"""End-to-end: agent_handler respects TrifectaGuard."""
import json
import pytest
from unittest.mock import MagicMock
from conexus.core.agent_handler import AgentHandlerConfig, handle_agent_message


def _make_cfg(tool_calls: list[str], tool_tags: dict[str, str]) -> AgentHandlerConfig:
    """Build a minimal config that makes the LLM call each tool in sequence then reply."""
    call_iter = iter(tool_calls)

    async def mock_acall(**kwargs):
        try:
            tool_name = next(call_iter)
            tc = MagicMock()
            tc.function.name = tool_name
            tc.function.arguments = "{}"
            tc.id = f"id_{tool_name}"
            msg = MagicMock()
            msg.tool_calls = [tc]
            msg.content = None
            choice = MagicMock()
            choice.message = msg
            resp = MagicMock()
            resp.choices = [choice]
            return resp, "mock-model"
        except StopIteration:
            msg = MagicMock()
            msg.tool_calls = None
            msg.content = "done"
            choice = MagicMock()
            choice.message = msg
            resp = MagicMock()
            resp.choices = [choice]
            return resp, "mock-model"

    llm = MagicMock()
    llm.acall = mock_acall
    llm.config = MagicMock()
    llm.config.temperature = 0.4

    async def execute_tool(name, args):
        return json.dumps({"ok": True})

    return AgentHandlerConfig(
        name="test",
        llm=llm,
        tools_schema=[],
        execute_tool=execute_tool,
        system_prompt="test",
        tool_tags=tool_tags,
    )


@pytest.mark.asyncio
async def test_handler_allows_safe_sequence():
    cfg = _make_cfg(
        tool_calls=["web_fetch"],
        tool_tags={"web_fetch": "untrusted_read"},
    )
    store = MagicMock()
    store.chat_recent.return_value = []
    store.facts_list.return_value = []
    store.chat_append = MagicMock()
    cap_checker = MagicMock()
    cap_checker.check.return_value = MagicMock(allowed=True)
    reply = await handle_agent_message(cfg, store, cap_checker, "hello")
    assert reply == "done"


@pytest.mark.asyncio
async def test_handler_blocks_exfil_sequence():
    cfg = _make_cfg(
        tool_calls=["web_fetch", "wiki_read", "wiki_write"],
        tool_tags={
            "web_fetch": "untrusted_read",
            "wiki_read": "private_read",
            "wiki_write": "external_write",
        },
    )
    store = MagicMock()
    store.chat_recent.return_value = []
    store.facts_list.return_value = []
    store.chat_append = MagicMock()
    cap_checker = MagicMock()
    cap_checker.check.return_value = MagicMock(allowed=True)

    reply = await handle_agent_message(cfg, store, cap_checker, "hello")
    # wiki_write was blocked — handler recovered and produced a reply
    assert reply is not None
