"""tool_audit table + record_tool_call."""
from __future__ import annotations
import json
import sqlite3
from conexus.core.memory.tool_audit import init_tool_audit, record_tool_call


def test_init_creates_table(tmp_path):
    conn = sqlite3.connect(tmp_path / "a.db")
    init_tool_audit(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tool_audit)").fetchall()}
    assert {"id", "ts", "session_id", "agent", "tool", "args_json", "result", "outcome"} <= cols


def test_record_round_trip(tmp_path):
    conn = sqlite3.connect(tmp_path / "a.db")
    init_tool_audit(conn)
    record_tool_call(
        conn,
        session_id="sess-1",
        agent="ana",
        tool="search",
        args={"q": "weather"},
        result='"hot"',
        outcome="ok",
    )
    rows = conn.execute(
        "SELECT session_id, agent, tool, args_json, result, outcome FROM tool_audit"
    ).fetchall()
    assert rows == [("sess-1", "ana", "search", json.dumps({"q": "weather"}), '"hot"', "ok")]


def test_init_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "a.db")
    init_tool_audit(conn)
    init_tool_audit(conn)  # must not raise
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tool_audit)").fetchall()}
    assert "session_id" in cols
