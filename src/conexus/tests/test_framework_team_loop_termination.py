"""max_parallel_members + termination_text loop wiring."""
from __future__ import annotations
import pytest
from conexus.core.team.team_pack import TeamPolicy
from conexus.core.agent_handler import AgentHandlerConfig, handle_team_message
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.budget.cap_checker import CapChecker
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry
from conexus.tests.test_framework_team_loop import FakeLLM, _msg_text, team as team_fixture  # noqa: F401


def test_team_policy_default_max_parallel_members_is_one():
    p = TeamPolicy()
    assert p.max_parallel_members == 1


def test_team_policy_accepts_override():
    p = TeamPolicy(max_parallel_members=3)
    assert p.max_parallel_members == 3


def test_team_policy_rejects_zero_max_parallel():
    with pytest.raises(Exception):  # pydantic ValidationError
        TeamPolicy(max_parallel_members=0)


@pytest.mark.asyncio
async def test_termination_text_ends_loop(tmp_path, team_fixture):
    """If starter emits text containing policy.termination_text, loop returns it as final."""
    store = SqliteStore(":memory:")

    async def exec_tool(name, args):
        return "{}"

    ana_cfg = AgentHandlerConfig(
        name="ana", llm=FakeLLM(script=[_msg_text("All done DONE.")]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="ana", tool_tags=None,
    )
    res_cfg = AgentHandlerConfig(
        name="researcher", llm=FakeLLM(script=[]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="researcher", tool_tags=None,
    )
    reply = await handle_team_message(
        team=team_fixture,
        configs={"ana": ana_cfg, "researcher": res_cfg},
        store=store,
        cap_checker=CapChecker(store),
        body="please go",
    )
    assert reply == "All done DONE."
