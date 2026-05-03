"""Token-budget compactor with rolling summary + verbatim recency tail."""
from __future__ import annotations

import pytest

from conexus.core.config.skill_loader import HistorySection
from conexus.core.history.compactor import HistoryCompactor, build_history
from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(str(tmp_path / "hist.db"))
    s.init_db()
    return s


def _approx_tokens(text: str) -> int:
    """Stub tokenizer: 4 chars ~ 1 token (matches OpenAI's rule of thumb)."""
    return max(1, len(text) // 4)


def test_empty_history_returns_only_persona(store):
    cfg = HistorySection(budget_tokens=4000, keep_verbatim=6, summary_budget=800, trigger_pct=0.80)
    compactor = HistoryCompactor(store, cfg, summarize_fn=lambda old, new: "summary", token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    assert result.summary is None
    assert result.verbatim_messages == []
    assert result.compaction_triggered is False


def test_short_history_no_compaction(store):
    cfg = HistorySection(budget_tokens=4000, keep_verbatim=6, summary_budget=800, trigger_pct=0.80)
    for i in range(3):
        store.chat_append("ana", "user", f"msg-{i}")
    compactor = HistoryCompactor(store, cfg, summarize_fn=lambda old, new: "summary", token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    assert len(result.verbatim_messages) == 3
    assert result.compaction_triggered is False


def test_overflow_triggers_compaction(store):
    """When older messages don't fit budget AND total >80%, compact them."""
    # 100 long messages, each ~200 tokens (800 chars)
    big = "x" * 800
    for _ in range(100):
        store.chat_append("ana", "user", big)
    cfg = HistorySection(budget_tokens=2000, keep_verbatim=6, summary_budget=400, trigger_pct=0.80)
    captured = {"old": None, "new_count": 0}
    def fake_summarize(old, new):
        captured["old"] = old
        captured["new_count"] = len(new)
        return "compacted summary"
    compactor = HistoryCompactor(store, cfg, summarize_fn=fake_summarize, token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    assert result.compaction_triggered is True
    assert result.summary == "compacted summary"
    assert len(result.verbatim_messages) >= 6  # at least the pinned tail
    # Persisted summary
    saved = store.summary_get("ana", "default")
    assert saved["summary_text"] == "compacted summary"


def test_compaction_uses_existing_summary(store):
    """Second compaction folds prior summary into new one."""
    store.summary_set("ana", "default", "prior summary", covers_until_msg_id=5, token_count=100)
    big = "y" * 800
    for _ in range(50):
        store.chat_append("ana", "user", big)
    cfg = HistorySection(budget_tokens=2000, keep_verbatim=6, summary_budget=400, trigger_pct=0.80)
    captured = {}
    def fake_summarize(old, new):
        captured["old"] = old
        return "merged"
    compactor = HistoryCompactor(store, cfg, summarize_fn=fake_summarize, token_fn=_approx_tokens)
    compactor.build("ana", "default")
    assert captured["old"] == "prior summary"


def test_keep_verbatim_always_pinned(store):
    """Last keep_verbatim turns are NEVER summarized away."""
    for i in range(20):
        store.chat_append("ana", "user", f"m{i}")
    cfg = HistorySection(budget_tokens=4000, keep_verbatim=5, summary_budget=400, trigger_pct=0.80)
    compactor = HistoryCompactor(store, cfg, summarize_fn=lambda o, n: "s", token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    last_5 = [m["content"] for m in result.verbatim_messages[-5:]]
    assert last_5 == ["m15", "m16", "m17", "m18", "m19"]
