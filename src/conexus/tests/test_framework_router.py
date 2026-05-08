from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from conexus.core.llm.context_tag import current_context, set_context
from conexus.core.llm.service import LLMConfig, build_llm
from conexus.core.llm.telemetry import install
from conexus.core.memory.sqlite_store import SqliteStore


def _make_store(tmp_db_path: Path) -> SqliteStore:
    store = SqliteStore(tmp_db_path)
    store.init_db()
    return store


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


@pytest.mark.asyncio
async def test_acomplete_text_returns_content(tmp_db_path):
    store = _make_store(tmp_db_path)
    install(store)
    llm = build_llm(
        LLMConfig(provider="gemini", model="gemini-2.0-flash"),
        "ana",
    )

    mock_resp = _mock_resp("Bom dia, Leandro!")
    with patch.object(llm._router, "acompletion", return_value=mock_resp):
        with set_context("briefing"):
            result = await llm.acomplete_text([{"role": "user", "content": "olá"}])

    assert result == "Bom dia, Leandro!"


@pytest.mark.asyncio
async def test_acompletion_handles_metadata(tmp_db_path):
    """Verify acompletion adds agent_name to metadata."""
    store = _make_store(tmp_db_path)
    install(store)
    llm = build_llm(
        LLMConfig(provider="gemini", model="gemini-2.0-flash"),
        "ana",
    )

    captured_metadata = {}

    async def capture_metadata(model, messages, **kw):
        captured_metadata.update(kw.get("metadata", {}))
        return _mock_resp("response")

    with patch.object(llm._router, "acompletion", side_effect=capture_metadata):
        await llm.acomplete_text([{"role": "user", "content": "test"}])

    assert captured_metadata.get("agent_name") == "ana"


@pytest.mark.asyncio
async def test_acompletion_raises_on_failure(tmp_db_path):
    store = _make_store(tmp_db_path)
    install(store)
    llm = build_llm(
        LLMConfig(provider="gemini", model="gemini-2.0-flash"),
        "ana",
    )

    with patch.object(llm._router, "acompletion", side_effect=RuntimeError("service error")):
        with pytest.raises(RuntimeError, match="service error"):
            await llm.acomplete_text([{"role": "user", "content": "test"}])
