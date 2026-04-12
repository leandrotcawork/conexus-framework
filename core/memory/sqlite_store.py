"""SQLite store for Conexus: facts, todos, chat_history, ping_log, llm_usage, failed_sends."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT NOT NULL,
    due         TEXT,
    done        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    done_at     TEXT
);

CREATE TABLE IF NOT EXISTS chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    ts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_history_agent_ts
    ON chat_history(agent_name, ts);

CREATE TABLE IF NOT EXISTS ping_log (
    kind        TEXT NOT NULL,
    ref_id      TEXT NOT NULL,
    agent_name  TEXT NOT NULL,
    sent_at     TEXT,
    PRIMARY KEY (kind, ref_id, agent_name)
);

CREATE TABLE IF NOT EXISTS llm_usage (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    agent_name     TEXT NOT NULL,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    input_tokens   INTEGER NOT NULL,
    output_tokens  INTEGER NOT NULL,
    cost_usd       REAL NOT NULL,
    context        TEXT NOT NULL,
    duration_ms    INTEGER,
    error          TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_agent_ts
    ON llm_usage(agent_name, ts);

CREATE TABLE IF NOT EXISTS failed_sends (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    error       TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    next_retry  TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ----- facts -----

    def fact_set(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO facts (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                                                  updated_at=excluded.updated_at""",
                (key, value, _now_iso()),
            )
            conn.commit()

    def fact_get(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM facts WHERE key=?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def facts_list(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value, updated_at FROM facts").fetchall()
            return [dict(r) for r in rows]

    # ----- todos -----

    def todo_add(self, text: str, due_iso: str | None = None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO todos (text, due, created_at) VALUES (?, ?, ?)""",
                (text, due_iso, _now_iso()),
            )
            conn.commit()
            return cur.lastrowid

    def todos_list(self, status: str = "open") -> list[dict]:
        where = {
            "open": "done=0",
            "done": "done=1",
            "all":  "1=1",
        }.get(status)
        if where is None:
            raise ValueError(f"invalid status: {status}")
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT id, text, due, done, created_at, done_at FROM todos WHERE {where} ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]

    def todo_mark_done(self, todo_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE todos SET done=1, done_at=? WHERE id=?",
                (_now_iso(), todo_id),
            )
            conn.commit()

    # ----- chat history -----

    def chat_append(self, agent_name: str, role: str, content: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO chat_history (agent_name, role, content, ts) VALUES (?, ?, ?, ?)",
                (agent_name, role, content, _now_iso()),
            )
            conn.commit()

    def chat_recent(self, agent_name: str, limit: int = 10) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id, agent_name, role, content, ts
                   FROM chat_history WHERE agent_name=?
                   ORDER BY id DESC LIMIT ?""",
                (agent_name, limit),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]  # oldest first

    # ----- ping log -----

    def ping_mark_pending(self, kind: str, ref_id: str, agent_name: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO ping_log (kind, ref_id, agent_name, sent_at)
                   VALUES (?, ?, ?, NULL)
                   ON CONFLICT(kind, ref_id, agent_name) DO NOTHING""",
                (kind, ref_id, agent_name),
            )
            conn.commit()

    def ping_mark_sent(self, kind: str, ref_id: str, agent_name: str) -> None:
        ts = _now_iso()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO ping_log (kind, ref_id, agent_name, sent_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(kind, ref_id, agent_name) DO UPDATE SET sent_at=excluded.sent_at""",
                (kind, ref_id, agent_name, ts),
            )
            conn.commit()

    def ping_was_sent(self, kind: str, ref_id: str, agent_name: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT sent_at FROM ping_log WHERE kind=? AND ref_id=? AND agent_name=?",
                (kind, ref_id, agent_name),
            ).fetchone()
            return row is not None and row["sent_at"] is not None
