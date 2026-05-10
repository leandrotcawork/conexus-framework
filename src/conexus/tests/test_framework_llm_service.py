"""Tests for LLMService — cache_control attachment."""
import asyncio
from unittest.mock import MagicMock

from conexus.core.llm.service import LLMConfig, LLMService, _apply_cache_control


# ---------------------------------------------------------------------------
# _apply_cache_control unit tests
# ---------------------------------------------------------------------------

def test_cache_control_converts_string_system_to_block():
    messages = [{"role": "system", "content": "stable system"}]
    out, _ = _apply_cache_control(messages, {})
    assert isinstance(out[0]["content"], list)
    assert out[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert out[0]["content"][0]["text"] == "stable system"


def test_cache_control_appends_to_existing_list_system():
    messages = [
        {"role": "system", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
    ]
    out, _ = _apply_cache_control(messages, {})
    blocks = out[0]["content"]
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
    assert blocks[0].get("cache_control") is None  # only last block


def test_cache_control_adds_to_last_tool():
    tools = [
        {"type": "function", "function": {"name": "a"}},
        {"type": "function", "function": {"name": "b"}},
    ]
    _, kw = _apply_cache_control([{"role": "system", "content": "x"}], {"tools": tools})
    assert kw["tools"][-1].get("cache_control") == {"type": "ephemeral"}
    assert kw["tools"][0].get("cache_control") is None


def test_cache_control_does_not_mutate_caller_data():
    original_messages = [{"role": "system", "content": "original"}]
    original_tools = [{"type": "function", "function": {"name": "t"}}]
    _apply_cache_control(original_messages, {"tools": original_tools})
    # caller's data unchanged
    assert original_messages[0]["content"] == "original"
    assert "cache_control" not in original_tools[-1]


def test_cache_control_off_leaves_messages_untouched():
    cfg = LLMConfig(provider="openai", model="gpt-4o-mini")
    svc = LLMService(cfg, agent_name="t")
    captured: dict = {}

    async def fake(model, messages, metadata, **kw):
        captured["m"] = messages
        return MagicMock(choices=[MagicMock(message=MagicMock(content="ok", tool_calls=None))])

    svc._router.acompletion = fake
    asyncio.run(svc.acompletion(messages=[{"role": "system", "content": "x"}]))
    assert captured["m"][0]["content"] == "x"


def test_cache_control_on_attaches_markers():
    cfg = LLMConfig(provider="anthropic", model="claude-3-5-haiku-latest")
    svc = LLMService(cfg, agent_name="t")
    captured: dict = {}

    async def fake(model, messages, metadata, **kw):
        captured["messages"] = messages
        captured["tools"] = kw.get("tools")
        return MagicMock(choices=[MagicMock(message=MagicMock(content="ok", tool_calls=None))])

    svc._router.acompletion = fake
    tools = [{"type": "function", "function": {"name": "ping"}}]
    asyncio.run(svc.acompletion(
        messages=[{"role": "system", "content": "stable"}, {"role": "user", "content": "hi"}],
        tools=tools,
        cache_control=True,
    ))
    sys_content = captured["messages"][0]["content"]
    assert isinstance(sys_content, list)
    assert sys_content[-1]["cache_control"] == {"type": "ephemeral"}
    assert captured["tools"][-1]["cache_control"] == {"type": "ephemeral"}
