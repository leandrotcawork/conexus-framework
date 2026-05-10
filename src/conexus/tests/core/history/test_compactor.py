"""Token-budget compactor with rolling summary + verbatim recency tail."""
from __future__ import annotations

import pytest

from conexus.core.config.skill_loader import HistorySection
from conexus.core.history.compactor import HistoryCompactor, build_history
from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(":memory:")
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


def test_leftover_under_trigger_does_not_compact(store):
    """Leftover exists (older too big to fit after pinned) but usage stays below trigger."""
    # 50 fat messages, ~150 tokens each (600 chars)
    fat = "x" * 600
    for _ in range(50):
        store.chat_append("ana", "user", fat)
    # keep_verbatim=2 → pinned=2 msgs ≈ 300 toks; budget=1000; budget_left≈700 fits ~4 more.
    # leftover = 50 - 2 - 4 = 44 msgs. usage ≈ 900/1000 = 0.90. trigger_pct=0.99 → no compact.
    cfg = HistorySection(budget_tokens=1000, keep_verbatim=2, summary_budget=400, trigger_pct=0.99)
    sentinel = {"called": False}

    def fake_summarize(old, new):
        sentinel["called"] = True
        return "should_not_happen"

    compactor = HistoryCompactor(store, cfg, summarize_fn=fake_summarize, token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    assert sentinel["called"] is False, "summarize should NOT be called when usage < trigger"
    assert store.summary_get("ana", "default") is None
    assert result.compaction_triggered is False


def test_resummarization_when_first_summary_too_large(store):
    """If summarize_fn returns text > summary_budget, it gets re-summarized once."""
    big = "y" * 800
    for _ in range(50):
        store.chat_append("ana", "user", big)
    cfg = HistorySection(budget_tokens=2000, keep_verbatim=6, summary_budget=100, trigger_pct=0.80)
    call_count = {"n": 0}

    def fake_summarize(old, new):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "x" * 1000  # way over 100-token budget (~250 tokens)
        return "tiny"  # second call returns small

    compactor = HistoryCompactor(store, cfg, summarize_fn=fake_summarize, token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    assert call_count["n"] == 2, "expected exactly 2 summarize calls (initial + re-summarize)"
    saved = store.summary_get("ana", "default")
    assert saved["summary_text"] == "tiny"


def test_summary_watermark_matches_leftover_last_id(store):
    """covers_until_msg_id must equal the highest msg_id folded into the summary."""
    big = "z" * 800
    for _ in range(50):
        store.chat_append("ana", "user", big)
    cfg = HistorySection(budget_tokens=2000, keep_verbatim=6, summary_budget=400, trigger_pct=0.80)
    captured = {}

    def fake_summarize(old, new):
        captured["new_msgs"] = new
        return "summary"

    compactor = HistoryCompactor(store, cfg, summarize_fn=fake_summarize, token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    assert result.compaction_triggered is True
    saved = store.summary_get("ana", "default")
    expected_watermark = captured["new_msgs"][-1]["id"]
    assert saved["covers_until_msg_id"] == expected_watermark
