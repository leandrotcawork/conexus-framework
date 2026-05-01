"""SQLite-backed audit log for cross-agent handoffs."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from conexus.core.team.handoff import Handoff

SCHEMA = """
CREATE TABLE IF NOT EXISTS handoff_audit (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL,
  from_agent      TEXT NOT NULL,
  to_agent        TEXT NOT NULL,
  hop_count       INTEGER NOT NULL,
  tags            TEXT NOT NULL,
  trust_cleared   INTEGER NOT NULL,
  payload_json    TEXT NOT NULL,
  outcome         TEXT NOT NULL
);
"""


def init_handoff_audit(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def record_handoff(conn: sqlite3.Connection, h: Handoff, outcome: str) -> None:
    conn.execute(
        "INSERT INTO handoff_audit (ts, from_agent, to_agent, hop_count, tags, trust_cleared, payload_json, outcome) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            h.from_agent,
            h.to_agent,
            h.hop_count,
            json.dumps(sorted(t.value for t in h.tags)),
            int(h.trust_boundary_cleared is not None),
            h.model_dump_json(),
            outcome,
        ),
    )
    conn.commit()
