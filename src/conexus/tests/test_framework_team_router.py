import pytest
from conexus.core.team.handoff import Handoff
from conexus.core.team.handoff_router import HandoffRouter
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry

PACK_MD = """---
name: t
version: 0.1.0
manager: pm
members: [ana, pm, researcher]
edges:
  - {from: pm, to: researcher, when: "task.kind == 'research'"}
  - {from: researcher, to: pm, auto: true}
budget:
  team_daily_usd: 1.0
  shares: {ana: 0.2, pm: 0.4, researcher: 0.4}
policy:
  max_hops: 3
---
"""


def _registry(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    loader = TeamLoader({"ana", "pm", "researcher"})
    return TeamRegistry(loader.load(tmp_path / "TEAM_PACK.md"))


def test_router_auto_edge_taken(tmp_path):
    router = HandoffRouter(_registry(tmp_path))
    h = Handoff(from_agent="researcher", to_agent="auto", payload={})
    target = router.route(h)
    assert target == "pm"


def test_router_when_edge_taken(tmp_path):
    router = HandoffRouter(_registry(tmp_path))
    h = Handoff(from_agent="pm", to_agent="auto", payload={"task": {"kind": "research"}})
    assert router.route(h) == "researcher"


def test_router_falls_back_to_manager(tmp_path):
    router = HandoffRouter(_registry(tmp_path))
    h = Handoff(from_agent="ana", to_agent="auto", payload={})
    assert router.route(h) == "pm"


def test_router_explicit_target_respected(tmp_path):
    router = HandoffRouter(_registry(tmp_path))
    h = Handoff(from_agent="ana", to_agent="researcher", payload={})
    assert router.route(h) == "researcher"


def test_router_unknown_target_raises(tmp_path):
    router = HandoffRouter(_registry(tmp_path))
    h = Handoff(from_agent="ana", to_agent="ghost", payload={})
    with pytest.raises(ValueError, match="unknown target"):
        router.route(h)
