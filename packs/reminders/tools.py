"""Reminders pack — set/list/cancel scheduled messages."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from conexus.core.memory.sqlite_store import SqliteStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReminderTools:
    _tool_schemas: ClassVar[dict] = {
        "set_reminder": {
            "description": "Schedule a recurring reminder using 5-field cron syntax."
        },
        "list_reminders": {
            "description": "List active reminders for this agent."
        },
        "cancel_reminder": {
            "description": "Cancel an active reminder by id."
        },
    }

    def __init__(self, store: SqliteStore, agent_name: str) -> None:
        self._store = store
        self._agent = agent_name

    def set_reminder(self, when_cron: str, message: str) -> int:
        with self._store.connect() as conn:
            cur = conn.execute(
                "INSERT INTO pack_reminders_jobs (agent_name, cron, message, created_at)"
                " VALUES (?, ?, ?, ?)",
                (self._agent, when_cron, message, _now_iso()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_reminders(self) -> list[dict]:
        with self._store.connect() as conn:
            rows = conn.execute(
                "SELECT id, cron, message, created_at FROM pack_reminders_jobs"
                " WHERE agent_name=? AND active=1 ORDER BY id",
                (self._agent,),
            ).fetchall()
            return [dict(r) for r in rows]

    def cancel_reminder(self, reminder_id: int) -> bool:
        with self._store.connect() as conn:
            cur = conn.execute(
                "UPDATE pack_reminders_jobs SET active=0 WHERE id=? AND agent_name=? AND active=1",
                (reminder_id, self._agent),
            )
            conn.commit()
            return cur.rowcount > 0


def create_tools(ctx: dict) -> ReminderTools:
    return ReminderTools(store=ctx["store"], agent_name=ctx["agent_name"])
