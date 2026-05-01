"""SQLite-backed audit log for tool calls (replay fidelity)."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_audit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  session_id  TEXT NOT NULL,
  agent       TEXT NOT NULL,
  tool        TEXT NOT NULL,
  args_json   TEXT NOT NULL,
  result      TEXT NOT NULL,
  outcome     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_audit_session ON tool_audit(session_id);
"""


def init_tool_audit(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def record_tool_call(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    agent: str,
    tool: str,
    args: dict[str, Any],
    result: str,
    outcome: str,
) -> None:
    conn.execute(
        "INSERT INTO tool_audit (ts, session_id, agent, tool, args_json, result, outcome) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            session_id, agent, tool,
            json.dumps(args, sort_keys=True),
            result, outcome,
        ),
    )
    conn.commit()
