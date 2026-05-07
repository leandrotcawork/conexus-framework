"""Identity blocks — char-budgeted mutable text buffers pinned in system prompt."""
from __future__ import annotations

from datetime import datetime, timezone

from conexus.core.memory.sqlite_store import SqliteStore


class BlockOverBudgetError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BlockStore:
    def __init__(self, store: SqliteStore):
        self._store = store

    def set(self, agent_id: str, name: str, content: str, budget_chars: int) -> None:
        if len(content) > budget_chars:
            raise BlockOverBudgetError(
                f"block {name!r} content ({len(content)} chars) exceeds budget ({budget_chars})"
            )
        with self._store.connect() as conn:
            conn.execute(
                """INSERT INTO identity_blocks (agent_id, name, content, budget_chars, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(agent_id, name) DO UPDATE SET
                       content=excluded.content,
                       budget_chars=excluded.budget_chars,
                       updated_at=excluded.updated_at""",
                (agent_id, name, content, budget_chars, _now_iso()),
            )
            conn.commit()

    def get(self, agent_id: str, name: str) -> str | None:
        with self._store.connect() as conn:
            row = conn.execute(
                "SELECT content FROM identity_blocks WHERE agent_id=? AND name=?",
                (agent_id, name),
            ).fetchone()
            return row["content"] if row else None

    def list(self, agent_id: str) -> list[dict]:
        with self._store.connect() as conn:
            rows = conn.execute(
                """SELECT name, content, budget_chars, updated_at
                   FROM identity_blocks WHERE agent_id=? ORDER BY name""",
                (agent_id,),
            ).fetchall()
            return [dict(r) for r in rows]
