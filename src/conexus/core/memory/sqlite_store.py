"""SQLite store for Conexus: facts, todos, chat_history, ping_log, llm_usage, failed_sends."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    agent_id    TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (agent_id, key)
);
CREATE INDEX IF NOT EXISTS idx_facts_agent_updated
    ON facts(agent_id, updated_at DESC);

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

CREATE TABLE IF NOT EXISTS identity_blocks (
    agent_id     TEXT NOT NULL,
    name         TEXT NOT NULL,
    content      TEXT NOT NULL,
    budget_chars INTEGER NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (agent_id, name)
);

CREATE TABLE IF NOT EXISTS chat_summaries (
    agent_name           TEXT NOT NULL,
    chat_id              TEXT NOT NULL,
    summary_text         TEXT NOT NULL,
    covers_until_msg_id  INTEGER NOT NULL,
    token_count          INTEGER NOT NULL,
    updated_at           TEXT NOT NULL,
    PRIMARY KEY (agent_name, chat_id)
);

CREATE TABLE IF NOT EXISTS oauth_pkce_state (
  nonce TEXT PRIMARY KEY,
  code_verifier TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
  user_id TEXT NOT NULL,
  server_url TEXT NOT NULL,
  access_token_enc BLOB NOT NULL,
  refresh_token_enc BLOB,
  expires_at INTEGER NOT NULL,
  scopes_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, server_url)
);

CREATE TABLE IF NOT EXISTS oauth_clients (
  authorization_server TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  client_secret_enc BLOB,
  registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS github_app_installs (
    agent_id        TEXT PRIMARY KEY,
    repo_slug       TEXT NOT NULL,
    installation_id INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pack_migrations (
    pack_id     TEXT NOT NULL,
    version     TEXT NOT NULL,
    applied_at  TEXT NOT NULL,
    PRIMARY KEY (pack_id, version)
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate_facts_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate legacy facts table (no agent_id) to scoped schema."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(facts)").fetchall()]
    if not cols or "agent_id" in cols:
        return  # fresh DB or already migrated
    conn.executescript("""
        ALTER TABLE facts RENAME TO facts_legacy;
        CREATE TABLE facts (
            agent_id    TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (agent_id, key)
        );
        INSERT INTO facts (agent_id, key, value, updated_at)
            SELECT '_legacy', key, value, updated_at FROM facts_legacy;
        DROP TABLE facts_legacy;
        CREATE INDEX IF NOT EXISTS idx_facts_agent_updated
            ON facts(agent_id, updated_at DESC);
    """)
    conn.commit()


class SqliteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def init_db(self) -> None:
        from conexus.core.memory.handoff_audit import init_handoff_audit
        from conexus.core.memory.tool_audit import init_tool_audit
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            _migrate_facts_v1_to_v2(conn)
            conn.executescript(SCHEMA)
            conn.commit()
            init_handoff_audit(conn)
            init_tool_audit(conn)

    @property
    def conn(self) -> sqlite3.Connection:
        """Open a direct connection to the DB. Caller is responsible for closing.

        Intended for audit queries in tests and for long-lived operations like
        handle_team_message that need a single connection across multiple writes.
        """
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ----- facts -----

    def fact_set(self, agent_id: str, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO facts (agent_id, key, value, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(agent_id, key) DO UPDATE SET value=excluded.value,
                                                       updated_at=excluded.updated_at""",
                (agent_id, key, value, _now_iso()),
            )
            conn.commit()

    def fact_get(self, agent_id: str, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM facts WHERE agent_id=? AND key=?",
                (agent_id, key),
            ).fetchone()
            return row["value"] if row else None

    def facts_list(self, agent_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT key, value, updated_at FROM facts WHERE agent_id=? ORDER BY key",
                (agent_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def facts_recent(self, agent_id: str, limit: int = 10) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT key, value, updated_at FROM facts
                   WHERE agent_id=? ORDER BY updated_at DESC LIMIT ?""",
                (agent_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def fact_delete(self, agent_id: str, key: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM facts WHERE agent_id=? AND key=?",
                (agent_id, key),
            )
            conn.commit()
            return cur.rowcount > 0

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

    def summary_get(self, agent_name: str, chat_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT summary_text, covers_until_msg_id, token_count, updated_at
                   FROM chat_summaries WHERE agent_name=? AND chat_id=?""",
                (agent_name, chat_id),
            ).fetchone()
            return dict(row) if row else None

    def summary_set(
        self,
        agent_name: str,
        chat_id: str,
        summary_text: str,
        covers_until_msg_id: int,
        token_count: int,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO chat_summaries
                       (agent_name, chat_id, summary_text, covers_until_msg_id, token_count, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(agent_name, chat_id) DO UPDATE SET
                       summary_text=excluded.summary_text,
                       covers_until_msg_id=excluded.covers_until_msg_id,
                       token_count=excluded.token_count,
                       updated_at=excluded.updated_at""",
                (agent_name, chat_id, summary_text, covers_until_msg_id, token_count, _now_iso()),
            )
            conn.commit()

    def chat_after(self, agent_name: str, chat_id: str, after_msg_id: int) -> list[dict]:
        """Fetch all messages with id > after_msg_id, oldest first.

        Note: chat_history has no chat_id column; chat_id param is accepted for
        API forward-compatibility but ignored — all history for the agent is one logical chat.
        """
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id, role, content, ts FROM chat_history
                   WHERE agent_name=? AND id > ? ORDER BY id ASC""",
                (agent_name, after_msg_id),
            ).fetchall()
            return [dict(r) for r in rows]

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

    # ----- pack migrations -----

    def apply_pack_migrations(self, pack_id: str, sql_dir: Path) -> None:
        """Apply unapplied SQL files in sql_dir alphabetically. Tracks via pack_migrations."""
        if not sql_dir.exists():
            return
        files = sorted(sql_dir.glob("*.sql"))
        with self.connect() as conn:
            applied = {
                r["version"] for r in conn.execute(
                    "SELECT version FROM pack_migrations WHERE pack_id=?", (pack_id,)
                ).fetchall()
            }
            for f in files:
                version = f.stem
                if version in applied:
                    continue
                conn.executescript(f.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO pack_migrations (pack_id, version, applied_at) VALUES (?, ?, ?)",
                    (pack_id, version, _now_iso()),
                )
                conn.commit()

    # ----- github app installs -----

    def github_app_install_set(
        self, agent_id: str, repo_slug: str, installation_id: int
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO github_app_installs (agent_id, repo_slug, installation_id, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(agent_id) DO UPDATE SET
                     repo_slug=excluded.repo_slug,
                     installation_id=excluded.installation_id,
                     created_at=excluded.created_at""",
                (agent_id, repo_slug, installation_id, _now_iso()),
            )
            conn.commit()

    def github_app_install_get(self, agent_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT agent_id, repo_slug, installation_id, created_at"
                " FROM github_app_installs WHERE agent_id=?",
                (agent_id,),
            ).fetchone()
        return dict(row) if row else None

    def github_app_install_delete(self, agent_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM github_app_installs WHERE agent_id=?", (agent_id,)
            )
            conn.commit()
