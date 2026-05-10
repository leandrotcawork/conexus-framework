"""End-to-end multi-agent delegate cycle with stubbed LLMs."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
import pytest
from conexus.core.agent_handler import AgentHandlerConfig, handle_team_message
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.budget.cap_checker import CapChecker
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry


def _msg_tool(call_id: str, fn_name: str, fn_args_json: str):
    return SimpleNamespace(
        tool_calls=[SimpleNamespace(
            id=call_id,
            function=SimpleNamespace(name=fn_name, arguments=fn_args_json),
        )],
        content=None,
    )


def _msg_text(text: str):
    return SimpleNamespace(tool_calls=None, content=text)


@dataclass
class FakeLLM:
    """Returns the next scripted message from `script` per call."""
    script: list[Any]
    config: Any = field(default_factory=lambda: SimpleNamespace(temperature=0.0))
    _i: int = 0

    async def acall(self, **kwargs):
        m = self.script[self._i]
        self._i += 1
        resp = SimpleNamespace(choices=[SimpleNamespace(message=m)])
        return resp, "fake-model"


@pytest.fixture
def team(tmp_path):
    p = tmp_path / "TEAM_PACK.md"
    p.write_text(
        "---\n"
        "name: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, researcher]\n"
        "edges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, researcher: 0.5}}\n"
        "policy: {max_hops: 5, max_turns: 5, termination_text: DONE}\n"
        "---\n"
    )
    doc = TeamLoader({"ana", "researcher"}).load(str(p))
    return TeamRegistry(doc)


@pytest.mark.asyncio
async def test_delegate_yields_then_returns(tmp_path, team):
    db = tmp_path / "c.db"
    store = SqliteStore(str(db))

    async def exec_tool_ana(name, args):
        return "{}"

    async def exec_tool_research(name, args):
        return '"web result: X is foo"'

    ana_cfg = AgentHandlerConfig(
        name="ana",
        llm=FakeLLM(script=[
            _msg_tool("c1", "delegate_to_researcher", '{"task": {"goal": "look up X"}}'),
            _msg_text("Final answer based on research."),
        ]),
        tools_schema=[],
        execute_tool=exec_tool_ana,
        system_prompt="you are ana",
        tool_tags=None,
    )
    researcher_cfg = AgentHandlerConfig(
        name="researcher",
        llm=FakeLLM(script=[
            _msg_text("X is foo."),
        ]),
        tools_schema=[],
        execute_tool=exec_tool_research,
        system_prompt="you are researcher",
        tool_tags=None,
    )

    cap_checker = CapChecker(store)
    reply = await handle_team_message(
        team=team,
        configs={"ana": ana_cfg, "researcher": researcher_cfg},
        store=store,
        cap_checker=cap_checker,
        body="please find X",
        session_id="sess-test-1",
    )
    assert reply == "Final answer based on research."


@pytest.mark.asyncio
async def test_return_on_short_circuits(tmp_path, team):
    db = tmp_path / "c.db"
    store = SqliteStore(str(db))

    async def exec_tool_any(name, args):
        return "{}"

    ana_cfg = AgentHandlerConfig(
        name="ana",
        llm=FakeLLM(script=[
            _msg_tool("c1", "delegate_to_researcher",
                      '{"task": {"goal": "x"}, "return_on": "RESULT_OK"}'),
            _msg_text("Done."),
        ]),
        tools_schema=[],
        execute_tool=exec_tool_any,
        system_prompt="ana",
        tool_tags=None,
    )
    researcher_cfg = AgentHandlerConfig(
        name="researcher",
        llm=FakeLLM(script=[
            _msg_text("RESULT_OK: foo"),
        ]),
        tools_schema=[],
        execute_tool=exec_tool_any,
        system_prompt="researcher",
        tool_tags=None,
    )

    cap_checker = CapChecker(store)
    reply = await handle_team_message(
        team=team, configs={"ana": ana_cfg, "researcher": researcher_cfg},
        store=store, cap_checker=cap_checker, body="x",
        session_id="sess-ret",
    )
    assert reply == "Done."


@pytest.mark.asyncio
async def test_nested_delegation_success(tmp_path):
    """ana → researcher → pm chain, all return naturally, hop_count chains."""
    pack = tmp_path / "TEAM_PACK.md"
    pack.write_text(
        "---\nname: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, researcher, pm]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.4, researcher: 0.3, pm: 0.3}}\n"
        "policy: {max_hops: 5, max_turns: 6, termination_text: DONE}\n---\n"
    )
    doc = TeamLoader({"ana", "researcher", "pm"}).load(str(pack))
    team = TeamRegistry(doc)
    store = SqliteStore(":memory:")

    async def exec_tool(name, args):
        return "{}"

    ana = AgentHandlerConfig(
        name="ana", llm=FakeLLM(script=[
            _msg_tool("c1", "delegate_to_researcher", '{"task": {"q": "x"}}'),
            _msg_text("Final ana DONE."),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="ana", tool_tags=None,
    )
    res = AgentHandlerConfig(
        name="researcher", llm=FakeLLM(script=[
            _msg_tool("c2", "delegate_to_pm", '{"task": {"r": "y"}}'),
            _msg_text("researcher reply"),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="researcher", tool_tags=None,
    )
    pm = AgentHandlerConfig(
        name="pm", llm=FakeLLM(script=[
            _msg_text("pm reply"),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="pm", tool_tags=None,
    )
    cap_checker = CapChecker(store)
    reply = await handle_team_message(
        team=team, configs={"ana": ana, "researcher": res, "pm": pm},
        store=store, cap_checker=cap_checker, body="go",
        session_id="sess-nested",
    )
    assert reply == "Final ana DONE."
    conn = store.conn
    try:
        rows = conn.execute(
            "SELECT from_agent, to_agent, hop_count FROM handoff_audit WHERE session_id=? ORDER BY id",
            ("sess-nested",),
        ).fetchall()
        assert [(r[0], r[1], r[2]) for r in rows] == [("ana", "researcher", 0), ("researcher", "pm", 1)]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_hop_limit_aborts(tmp_path):
    """Nested delegation exceeding policy.max_hops surfaces as tool error."""
    pack = tmp_path / "TEAM_PACK.md"
    pack.write_text(
        "---\nname: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, researcher]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, researcher: 0.5}}\n"
        "policy: {max_hops: 1, max_turns: 6, termination_text: DONE}\n---\n"
    )
    doc = TeamLoader({"ana", "researcher"}).load(str(pack))
    team = TeamRegistry(doc)
    store = SqliteStore(":memory:")

    async def exec_tool(name, args):
        return "{}"

    ana_cfg = AgentHandlerConfig(
        name="ana", llm=FakeLLM(script=[
            _msg_tool("c1", "delegate_to_researcher", '{"task": {"x": 1}}'),
            _msg_text("Aborted DONE."),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="ana", tool_tags=None,
    )
    res_cfg = AgentHandlerConfig(
        name="researcher", llm=FakeLLM(script=[
            _msg_tool("c2", "delegate_to_ana", '{"task": {"y": 2}}'),
            _msg_text("RESULT done"),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="researcher", tool_tags=None,
    )
    cap_checker = CapChecker(store)
    reply = await handle_team_message(
        team=team, configs={"ana": ana_cfg, "researcher": res_cfg},
        store=store, cap_checker=cap_checker, body="go",
        session_id="sess-hop",
    )
    assert reply == "Aborted DONE."


@pytest.mark.asyncio
async def test_tool_audit_records_non_delegate_calls(tmp_path, team):
    """Every non-delegate execute_tool must produce a tool_audit row."""
    db = tmp_path / "c.db"
    store = SqliteStore(str(db))

    async def exec_tool(name, args):
        return '"foo"'

    ana_cfg = AgentHandlerConfig(
        name="ana", llm=FakeLLM(script=[
            _msg_tool("c1", "search", '{"q": "weather"}'),
            _msg_text("All good DONE."),
        ]),
        tools_schema=[{"type": "function", "function": {"name": "search",
                       "parameters": {"type": "object"}}}],
        execute_tool=exec_tool,
        system_prompt="ana", tool_tags=None,
    )
    res_cfg = AgentHandlerConfig(
        name="researcher", llm=FakeLLM(script=[]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="researcher", tool_tags=None,
    )
    cap_checker = CapChecker(store)
    await handle_team_message(
        team=team, configs={"ana": ana_cfg, "researcher": res_cfg},
        store=store, cap_checker=cap_checker, body="go",
        session_id="sess-audit",
    )
    conn = store.conn
    try:
        rows = conn.execute(
            "SELECT agent, tool, outcome FROM tool_audit WHERE session_id=?",
            ("sess-audit",),
        ).fetchall()
        assert ("ana", "search", "ok") in [(r[0], r[1], r[2]) for r in rows]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_trifecta_propagates_through_handoff(tmp_path):
    """Child agent's TrifectaGuard must inherit parent's taint via Handoff.tags."""
    from conexus.core.trifecta.tags import DataClass
    pack = tmp_path / "TEAM_PACK.md"
    pack.write_text(
        "---\nname: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, pm]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, pm: 0.5}}\n---\n"
    )
    doc = TeamLoader({"ana", "pm"}).load(str(pack))
    team = TeamRegistry(doc)
    store = SqliteStore(":memory:")

    async def exec_tool(name, args):
        return '"x"'

    ana_cfg = AgentHandlerConfig(
        name="ana", llm=FakeLLM(script=[
            _msg_tool("c1", "fetch_url", '{"url": "x"}'),
            _msg_tool("c2", "read_secrets", '{"k": "y"}'),
            _msg_tool("c3", "delegate_to_pm", '{"task": {"x": 1}}'),
            _msg_text("Done DONE."),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="ana",
        tool_tags={
            "fetch_url": "untrusted_read",
            "read_secrets": "private_read",
            "send_email": "external_write",
        },
    )
    pm_cfg = AgentHandlerConfig(
        name="pm", llm=FakeLLM(script=[
            _msg_tool("c2", "send_email", '{"to": "x"}'),
            _msg_text("RESULT (blocked)"),
        ]),
        tools_schema=[{"type": "function", "function": {"name": "send_email",
                       "parameters": {"type": "object"}}}],
        execute_tool=exec_tool,
        system_prompt="pm",
        tool_tags={"send_email": "external_write"},
    )
    cap_checker = CapChecker(store)
    await handle_team_message(
        team=team, configs={"ana": ana_cfg, "pm": pm_cfg},
        store=store, cap_checker=cap_checker, body="go",
        session_id="sess-tri",
    )
    conn = store.conn
    try:
        rows = conn.execute(
            "SELECT agent, tool, outcome FROM tool_audit WHERE session_id=?",
            ("sess-tri",),
        ).fetchall()
        assert ("pm", "send_email", "trifecta_blocked") in [(r[0], r[1], r[2]) for r in rows]
    finally:
        conn.close()
