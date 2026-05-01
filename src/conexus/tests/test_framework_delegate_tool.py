"""delegate_to_<agent> LLM tool schema generation + arg parsing."""
from __future__ import annotations
import pytest
from conexus.core.team.delegate_tool import (
    build_delegate_schemas,
    parse_delegate_call,
    DELEGATE_PREFIX,
)
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry


@pytest.fixture
def team(tmp_path):
    p = tmp_path / "TEAM_PACK.md"
    p.write_text(
        "---\n"
        "name: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, pm, researcher]\n"
        "edges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.4, pm: 0.3, researcher: 0.3}}\n"
        "---\n"
    )
    doc = TeamLoader({"ana", "pm", "researcher"}).load(str(p))
    return TeamRegistry(doc)


def test_build_delegate_schemas_one_per_member_minus_self(team):
    schemas = build_delegate_schemas(team, current_agent="ana")
    names = {s["function"]["name"] for s in schemas}
    assert names == {"delegate_to_pm", "delegate_to_researcher"}


def test_schema_has_required_payload_field(team):
    [s] = [s for s in build_delegate_schemas(team, "ana") if s["function"]["name"] == "delegate_to_pm"]
    params = s["function"]["parameters"]
    assert params["properties"]["task"]["type"] == "object"
    assert "task" in params["required"]


def test_parse_delegate_call_returns_target_and_payload():
    target, payload, opts = parse_delegate_call(
        f"{DELEGATE_PREFIX}pm",
        {"task": {"goal": "review design doc"}},
    )
    assert target == "pm"
    assert payload == {"task": {"goal": "review design doc"}}
    assert opts == {}


def test_parse_delegate_call_extracts_optional_overrides():
    _, _, opts = parse_delegate_call(
        f"{DELEGATE_PREFIX}pm",
        {"task": {"x": 1}, "context_mode": "full", "return_on": "DONE"},
    )
    assert opts == {"context_mode": "full", "return_on": "DONE"}


def test_parse_delegate_call_rejects_non_delegate_name():
    with pytest.raises(ValueError):
        parse_delegate_call("send_email", {})


def test_parse_delegate_call_rejects_unknown_context_mode():
    with pytest.raises(ValueError):
        parse_delegate_call(
            f"{DELEGATE_PREFIX}pm",
            {"task": {}, "context_mode": "bogus"},
        )
