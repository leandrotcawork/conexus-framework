"""Deterministic replay of frozen handoff_audit + tool_audit traces."""
from __future__ import annotations
import sqlite3
import pytest
from conexus.core.memory.handoff_audit import init_handoff_audit, record_handoff
from conexus.core.memory.tool_audit import init_tool_audit, record_tool_call
from conexus.core.team.handoff import Handoff
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry
from conexus.core.team.replay import replay_session, ReplayMismatch


@pytest.fixture
def db_with_team(tmp_path):
    pack = tmp_path / "TEAM_PACK.md"
    pack.write_text(
        "---\n"
        "name: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, researcher]\n"
        "edges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, researcher: 0.5}}\n"
        "---\n"
    )
    db = tmp_path / "c.db"
    conn = sqlite3.connect(db)
    init_handoff_audit(conn)
    init_tool_audit(conn)
    h = Handoff(from_agent="ana", to_agent="researcher", payload={"task": {"q": "x"}})
    record_handoff(conn, h, "routed", session_id="s1")
    record_tool_call(conn, session_id="s1", agent="researcher", tool="search",
                     args={"q": "x"}, result='"foo"', outcome="ok")
    conn.commit()
    doc = TeamLoader({"ana", "researcher"}).load(str(pack))
    return conn, TeamRegistry(doc)


def test_replay_succeeds_when_routes_unchanged(db_with_team):
    conn, registry = db_with_team
    report = replay_session(conn, session_id="s1", registry=registry)
    assert report.handoffs_replayed == 1
    assert report.tools_replayed == 1
    assert report.mismatches == []


def test_replay_detects_routing_change(tmp_path):
    pack_a = tmp_path / "v1.md"
    pack_a.write_text(
        "---\nname: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, researcher]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, researcher: 0.5}}\n---\n"
    )
    db = tmp_path / "c.db"
    conn = sqlite3.connect(db)
    init_handoff_audit(conn)
    init_tool_audit(conn)
    h = Handoff(from_agent="ana", to_agent="researcher", payload={})
    record_handoff(conn, h, "routed", session_id="s1")
    pack_b = tmp_path / "v2.md"
    pack_b.write_text(
        "---\nname: t\nversion: '2'\nmanager: ana\n"
        "members: [ana, pm]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, pm: 0.5}}\n---\n"
    )
    doc_b = TeamLoader({"ana", "pm"}).load(str(pack_b))
    report = replay_session(conn, session_id="s1", registry=TeamRegistry(doc_b))
    assert report.mismatches != []
    assert any(isinstance(m, ReplayMismatch) and m.kind == "route" for m in report.mismatches)
