from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.llm.context_tag import current_context, set_context
from core.llm.router import LLMConfig, TrackedLLM, build_llm
from core.llm.usage_tracker import UsageTracker
from core.memory.sqlite_store import SqliteStore


def _make_tracker(tmp_db_path: Path) -> UsageTracker:
    store = SqliteStore(tmp_db_path)
    store.init_db()
    return UsageTracker(store)


def _mock_resp(text: str) -> MagicMock:
    """Build a minimal litellm-style response mock."""
    choice = MagicMock()
    choice.message.content = text
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage.prompt_tokens = 100
    resp.usage.completion_tokens = 50
    # Make isinstance(resp, dict) → False
    resp.__class__ = MagicMock  # remains a MagicMock, not dict
    return resp


def test_context_tag_isolation():
    assert current_context() == "unknown"
    with set_context("briefing"):
        assert current_context() == "briefing"
        with set_context("pre_event"):
            assert current_context() == "pre_event"
        assert current_context() == "briefing"
    assert current_context() == "unknown"


def test_complete_logs_usage(tmp_db_path):
    tracker = _make_tracker(tmp_db_path)
    llm = build_llm(
        LLMConfig(provider="gemini", model="gemini-2.0-flash"),
        tracker,
        "ana",
    )

    mock_resp = _mock_resp("Bom dia, Leandro!")
    with patch("litellm.completion", return_value=mock_resp) as mock_lit:
        with set_context("briefing"):
            result = llm.complete([{"role": "user", "content": "olá"}])

    assert result == "Bom dia, Leandro!"
    rows = tracker.recent(agent_name="ana")
    assert len(rows) == 1
    assert rows[0]["context"] == "briefing"
    assert rows[0]["provider"] == "gemini"
    assert rows[0]["model"] == "gemini-2.0-flash"


def test_fallback_on_error(tmp_db_path):
    tracker = _make_tracker(tmp_db_path)
    llm = build_llm(
        LLMConfig(
            provider="gemini",
            model="gemini-2.0-flash",
            fallback=[{"provider": "openai", "model": "gpt-4o-mini"}],
        ),
        tracker,
        "ana",
    )

    def fail_then_succeed(model, messages, **kwargs):
        if "gemini" in model:
            raise RuntimeError("quota exceeded")
        return _mock_resp("fallback response")

    with patch("litellm.completion", side_effect=fail_then_succeed):
        result = llm.complete([{"role": "user", "content": "test"}])

    assert result == "fallback response"
    rows = tracker.recent(agent_name="ana")
    # Two rows: one failed (gemini), one succeeded (openai)
    assert len(rows) == 2
    failed = next(r for r in rows if r["error"])
    succeeded = next(r for r in rows if not r["error"])
    assert "gemini" in failed["provider"]
    assert "openai" in succeeded["provider"]


def test_all_providers_fail(tmp_db_path):
    tracker = _make_tracker(tmp_db_path)
    llm = build_llm(
        LLMConfig(
            provider="gemini",
            model="gemini-2.0-flash",
            fallback=[{"provider": "openai", "model": "gpt-4o-mini"}],
        ),
        tracker,
        "ana",
    )

    with patch("litellm.completion", side_effect=RuntimeError("all down")):
        with pytest.raises(RuntimeError, match="all down"):
            llm.complete([{"role": "user", "content": "test"}])
