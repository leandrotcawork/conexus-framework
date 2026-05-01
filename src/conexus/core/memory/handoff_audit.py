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
  session_id      TEXT NOT NULL DEFAULT 'legacy',
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
    cols = {r[1] for r in conn.execute("PRAGMA table_info(handoff_audit)").fetchall()}
    if "session_id" not in cols:
        conn.execute("ALTER TABLE handoff_audit ADD COLUMN session_id TEXT NOT NULL DEFAULT 'legacy'")
    conn.commit()


def record_handoff(
    conn: sqlite3.Connection, h: Handoff, outcome: str, *, session_id: str = "legacy"
) -> None:
    conn.execute(
        "INSERT INTO handoff_audit (ts, session_id, from_agent, to_agent, hop_count, "
        "tags, trust_cleared, payload_json, outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            session_id,
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
