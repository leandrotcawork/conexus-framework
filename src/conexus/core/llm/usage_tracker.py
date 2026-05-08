"""UsageTracker — read-only queries over the llm_usage table.

Writes are owned by conexus.core.llm.telemetry.UsageLogger (registered as a
litellm CustomLogger). This class only reads + aggregates.
"""
from __future__ import annotations

from datetime import datetime

from conexus.core.memory.sqlite_store import SqliteStore


class UsageTracker:
    def __init__(self, store: SqliteStore):
        self.store = store

    def recent(self, *, agent_name: str | None = None, limit: int = 50) -> list[dict]:
        with self.store.connect() as conn:
            if agent_name:
                rows = conn.execute(
                    "SELECT * FROM llm_usage WHERE agent_name=? ORDER BY id DESC LIMIT ?",
                    (agent_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM llm_usage ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def _rows(
        self,
        *,
        agent_name: str | None = None,
        since: datetime | None = None,
    ) -> list[dict]:
        where: list[str] = ["error IS NULL"]
        params: list = []
        if agent_name:
            where.append("agent_name=?")
            params.append(agent_name)
        if since:
            where.append("ts >= ?")
            params.append(since.isoformat())
        sql = "SELECT provider, model, input_tokens, output_tokens, context, cost_usd FROM llm_usage WHERE " + " AND ".join(where)
        with self.store.connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def total_usd(
        self,
        *,
        agent_name: str | None = None,
        since: datetime | None = None,
    ) -> float:
        with self.store.connect() as conn:
            where: list[str] = ["error IS NULL", "cost_usd IS NOT NULL"]
            params: list = []
            if agent_name:
                where.append("agent_name=?")
                params.append(agent_name)
            if since:
                where.append("ts >= ?")
                params.append(since.isoformat())
            sql = "SELECT COALESCE(SUM(cost_usd), 0.0) FROM llm_usage WHERE " + " AND ".join(where)
            return conn.execute(sql, params).fetchone()[0]

    def by_context(
        self,
        *,
        agent_name: str | None = None,
        since: datetime | None = None,
    ) -> dict[str, float]:
        totals: dict[str, float] = {}
        for r in self._rows(agent_name=agent_name, since=since):
            totals[r["context"]] = totals.get(r["context"], 0.0) + (r.get("cost_usd") or 0.0)
        return totals
