"""Tests for the unified agent message handler."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from conexus.core.agent_handler import AgentHandlerConfig, handle_agent_message
from conexus.core.budget.cap_checker import BudgetCap, CapChecker
from conexus.core.memory.sqlite_store import SqliteStore


def _mock_choice(content: str | None = None, tool_calls: list | None = None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    if tool_calls is None:
        msg.model_dump = lambda exclude_unset=False: {"role": "assistant", "content": content}
    else:
        msg.model_dump = lambda exclude_unset=False: {
            "role": "assistant",
            "tool_calls": [
                {"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        }
    return SimpleNamespace(message=msg)


def _mock_resp(content: str | None = None, tool_calls: list | None = None):
    return SimpleNamespace(choices=[_mock_choice(content, tool_calls)])


def _mock_tool_call(call_id: str, name: str, args: dict):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _make_config(tmp_db: Path, *, llm_responses: list, execute_tool=None, cap=None, max_turns=5):
    llm = MagicMock()
    llm.config = SimpleNamespace(temperature=0.4)
    responses = iter(llm_responses)
    llm.acall = AsyncMock(side_effect=lambda **kw: (next(responses), "gemini/test"))
    cfg = AgentHandlerConfig(
        name="ana",
        llm=llm,
        tools_schema=[],
        execute_tool=execute_tool or (lambda name, args: json.dumps({"ok": True})),
        system_prompt="SYSTEM",
        max_turns=max_turns,
        cap=cap,
    )
    return cfg


@pytest.mark.asyncio
async def test_text_reply_stored_and_returned(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    cap_checker = CapChecker(MagicMock())
    cfg = _make_config(tmp_db_path, llm_responses=[_mock_resp(content="Olá!")])

    reply = await handle_agent_message(cfg, store, cap_checker, "oi")

    assert reply == "Olá!"
    history = store.chat_recent("ana", limit=10)
    roles = [h["role"] for h in history]
    assert "user" in roles and "assistant" in roles


@pytest.mark.asyncio
async def test_cap_exceeded_short_circuits(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()

    # Force the cap to be exceeded — must be on_exceed="halt" for the
    # checker to actually block the request.
    cap = BudgetCap(daily_usd=0.0, monthly_usd=1.0, on_exceed="halt")
    fake_tracker = MagicMock()
    fake_tracker.total_usd.return_value = 999.0
    cap_checker = CapChecker(fake_tracker)

    cfg = _make_config(tmp_db_path, llm_responses=[], cap=cap)
    cfg.cap_exceeded_msg = "BLOCKED"

    reply = await handle_agent_message(cfg, store, cap_checker, "oi")

    assert reply == "BLOCKED"
    cfg.llm.acall.assert_not_called()


@pytest.mark.asyncio
async def test_tool_call_then_text_reply(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    cap_checker = CapChecker(MagicMock())

    calls: list[tuple[str, dict]] = []

    def fake_exec(name: str, args: dict) -> str:
        calls.append((name, args))
        return json.dumps({"result": 42})

    tc = _mock_tool_call("call1", "calendar_list_events", {"start_iso": "x", "end_iso": "y"})
    cfg = _make_config(
        tmp_db_path,
        llm_responses=[_mock_resp(tool_calls=[tc]), _mock_resp(content="Pronto!")],
        execute_tool=fake_exec,
    )

    reply = await handle_agent_message(cfg, store, cap_checker, "liste eventos")

    assert reply == "Pronto!"
    assert calls == [("calendar_list_events", {"start_iso": "x", "end_iso": "y"})]
    assert cfg.llm.acall.call_count == 2


@pytest.mark.asyncio
async def test_progress_callback_fires_once_per_tool(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    cap_checker = CapChecker(MagicMock())

    sent: list[str] = []

    async def send(msg: str) -> None:
        sent.append(msg)

    tc1 = _mock_tool_call("t1", "web_search", {"q": "a"})
    tc2 = _mock_tool_call("t2", "web_search", {"q": "b"})  # same tool, should not re-notify
    tc3 = _mock_tool_call("t3", "web_fetch", {"url": "u"})

    cfg = _make_config(
        tmp_db_path,
        llm_responses=[
            _mock_resp(tool_calls=[tc1, tc2]),
            _mock_resp(tool_calls=[tc3]),
            _mock_resp(content="done"),
        ],
    )
    cfg.progress_map = {"web_search": "searching", "web_fetch": "fetching"}

    await handle_agent_message(cfg, store, cap_checker, "go", progress=send)

    assert sent == ["searching", "fetching"]


@pytest.mark.asyncio
async def test_max_turns_exhausted_stores_fallback(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    cap_checker = CapChecker(MagicMock())

    tc = _mock_tool_call("c", "noop", {})
    # LLM keeps asking for the same tool forever; loop hits max_turns.
    cfg = _make_config(
        tmp_db_path,
        llm_responses=[_mock_resp(tool_calls=[tc])] * 10,
        max_turns=3,
    )
    cfg.fallback_msg = "FALLBACK"

    reply = await handle_agent_message(cfg, store, cap_checker, "hammer")

    assert reply == "FALLBACK"
    assert cfg.llm.acall.call_count == 3
    history = store.chat_recent("ana", limit=10)
    assert any(h["role"] == "user" and h["content"] == "hammer" for h in history)
    assert any(h["role"] == "assistant" and h["content"] == "FALLBACK" for h in history)


@pytest.mark.asyncio
async def test_tool_result_truncation(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    cap_checker = CapChecker(MagicMock())

    big = "x" * 100
    tc = _mock_tool_call("c", "big_tool", {})
    cfg = _make_config(
        tmp_db_path,
        llm_responses=[_mock_resp(tool_calls=[tc]), _mock_resp(content="ok")],
        execute_tool=lambda name, args: big,
    )
    cfg.result_max_chars = 10

    await handle_agent_message(cfg, store, cap_checker, "go")

    # Second acall message list should contain the truncated tool result
    second_call_kwargs = cfg.llm.acall.call_args_list[1].kwargs
    tool_msg = [m for m in second_call_kwargs["messages"] if m.get("role") == "tool"][0]
    assert tool_msg["content"].endswith("[... truncado]")
    assert len(tool_msg["content"]) <= 10 + len("\n[... truncado]")


@pytest.mark.asyncio
async def test_needs_auth_short_circuits(tmp_db_path):
    from conexus.core.oauth.errors import NeedsAuthError
    from conexus.core.agent_handler import NeedsAuthEvent

    events: list[NeedsAuthEvent] = []

    async def on_auth(ev: NeedsAuthEvent) -> None:
        events.append(ev)

    async def execute_tool(name: str, args: dict) -> str:
        raise NeedsAuthError("https://mcp.example/", ["calendar.read"])

    tc = _mock_tool_call("call1", "list_events", {})
    cfg = _make_config(
        tmp_db_path,
        llm_responses=[_mock_resp(tool_calls=[tc])],
        execute_tool=execute_tool,
    )
    cfg.tools_schema = [{"type": "function", "function": {"name": "list_events", "parameters": {}}}]
    cfg.on_auth_required = on_auth
    cfg.user_id = "user123"

    store = SqliteStore(tmp_db_path)
    store.init_db()
    cap_checker = CapChecker(MagicMock())

    reply = await handle_agent_message(cfg, store, cap_checker, "list my events")

    assert "permissão" in reply
    assert len(events) == 1
    assert events[0].server_url == "https://mcp.example/"
    assert events[0].user_id == "user123"


@pytest.mark.asyncio
async def test_system_prompt_stable_no_timestamp(tmp_db_path):
    """System message must NOT contain BRT timestamp after cache-control fix."""
    store = SqliteStore(tmp_db_path)
    store.init_db()
    cap_checker = CapChecker(MagicMock())

    captured_systems: list[str] = []

    def capturing_acall(**kw):
        msgs = kw.get("messages", [])
        sys_msg = next((m for m in msgs if m.get("role") == "system"), None)
        if sys_msg:
            content = sys_msg["content"]
            text = content if isinstance(content, str) else content[0]["text"]
            captured_systems.append(text)
        return (_mock_resp(content="ok"), "gemini/test")

    cfg = _make_config(tmp_db_path, llm_responses=[])
    cfg.llm.acall = AsyncMock(side_effect=capturing_acall)

    await handle_agent_message(cfg, store, cap_checker, "first")
    await handle_agent_message(cfg, store, cap_checker, "second")

    assert len(captured_systems) >= 2
    assert captured_systems[0] == captured_systems[1], "system prompt changed between calls"
    assert "BRT" not in captured_systems[0]
    assert "Data/hora" not in captured_systems[0]


@pytest.mark.asyncio
async def test_get_current_time_builtin_intercepted(tmp_db_path):
    """get_current_time builtin handled directly — not routed to execute_tool."""
    store = SqliteStore(tmp_db_path)
    store.init_db()
    cap_checker = CapChecker(MagicMock())
    execute_tool_calls: list[str] = []

    tc = _mock_tool_call("id1", "get_current_time", {})
    responses = iter([
        _mock_resp(tool_calls=[tc]),
        _mock_resp(content="done"),
    ])
    cfg = _make_config(
        tmp_db_path,
        llm_responses=[],
        execute_tool=lambda name, args: execute_tool_calls.append(name) or json.dumps({"ok": True}),
    )
    cfg.llm.acall = AsyncMock(side_effect=lambda **kw: (next(responses), "gemini/test"))

    reply = await handle_agent_message(cfg, store, cap_checker, "what time is it?")
    assert reply == "done"
    # execute_tool must NOT have been called for get_current_time
    assert "get_current_time" not in execute_tool_calls
