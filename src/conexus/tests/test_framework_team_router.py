import sqlite3

import pytest
from conexus.core.memory.handoff_audit import init_handoff_audit
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


def test_router_eval_blocks_dunder_traversal(tmp_path):
    """`when:` expressions must not allow `__class__`/`__subclasses__` escape."""
    pack = (
        "---\nname: t\nversion: 0.1.0\nmanager: pm\nmembers: [ana, pm]\n"
        "edges:\n  - {from: pm, to: ana, when: \"task.__class__.__bases__[0].__subclasses__()\"}\n"
        "budget:\n  team_daily_usd: 1.0\n  shares: {pm: 0.5, ana: 0.5}\npolicy:\n  max_hops: 3\n---\n"
    )
    (tmp_path / "TEAM_PACK.md").write_text(pack)
    reg = TeamRegistry(TeamLoader({"ana", "pm"}).load(tmp_path / "TEAM_PACK.md"))
    router = HandoffRouter(reg)
    h = Handoff(from_agent="pm", to_agent="auto", payload={"task": {"kind": "x"}})
    # Edge fails closed on illegal AST → falls back to manager (pm).
    assert router.route(h) == "pm"


def test_router_eval_blocks_function_calls(tmp_path):
    pack = (
        "---\nname: t\nversion: 0.1.0\nmanager: pm\nmembers: [ana, pm]\n"
        "edges:\n  - {from: pm, to: ana, when: \"len(task.kind) > 0\"}\n"
        "budget:\n  team_daily_usd: 1.0\n  shares: {pm: 0.5, ana: 0.5}\npolicy:\n  max_hops: 3\n---\n"
    )
    (tmp_path / "TEAM_PACK.md").write_text(pack)
    reg = TeamRegistry(TeamLoader({"ana", "pm"}).load(tmp_path / "TEAM_PACK.md"))
    router = HandoffRouter(reg)
    h = Handoff(from_agent="pm", to_agent="auto", payload={"task": {"kind": "x"}})
    # Call expr rejected → fallback to manager.
    assert router.route(h) == "pm"


def test_router_writes_audit_row(tmp_path):
    """Audit captures the original Handoff envelope (replay fidelity); outcome
    encodes resolution result."""
    conn = sqlite3.connect(":memory:")
    init_handoff_audit(conn)
    router = HandoffRouter(_registry(tmp_path), conn=conn)
    h = Handoff(from_agent="researcher", to_agent="auto", payload={})
    assert router.route(h) == "pm"
    rows = conn.execute(
        "SELECT from_agent, to_agent, outcome FROM handoff_audit"
    ).fetchall()
    assert rows == [("researcher", "auto", "routed")]


def test_router_writes_audit_on_unknown_target(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_handoff_audit(conn)
    router = HandoffRouter(_registry(tmp_path), conn=conn)
    h = Handoff(from_agent="ana", to_agent="ghost", payload={})
    with pytest.raises(ValueError):
        router.route(h)
    outcomes = [r[0] for r in conn.execute("SELECT outcome FROM handoff_audit").fetchall()]
    assert outcomes == ["unknown_target"]
