"""UsageTracker: logs every LLM call to the llm_usage table and aggregates totals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from core.llm.pricing import compute_cost
from core.memory.sqlite_store import SqliteStore


class UsageTracker:
    def __init__(self, store: SqliteStore):
        self.store = store

    def log_call(
        self,
        *,
        agent_name: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        context: str,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        full_model = f"{provider}/{model}"
        cost = compute_cost(full_model, input_tokens, output_tokens)
        ts = datetime.now(timezone.utc).isoformat()
        with self.store.connect() as conn:
            conn.execute(
                """INSERT INTO llm_usage
                   (ts, agent_name, provider, model, input_tokens, output_tokens,
                    cost_usd, context, duration_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, agent_name, provider, model, input_tokens, output_tokens,
                 cost, context, duration_ms, error),
            )
            conn.commit()

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

    def total_usd(
        self,
        *,
        agent_name: str | None = None,
        since: datetime | None = None,
    ) -> float:
        where: list[str] = []
        params: list = []
        if agent_name:
            where.append("agent_name=?")
            params.append(agent_name)
        if since:
            where.append("ts >= ?")
            params.append(since.isoformat())
        sql = "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM llm_usage"
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self.store.connect() as conn:
            row = conn.execute(sql, params).fetchone()
            return float(row["total"])

    def by_context(
        self,
        *,
        agent_name: str | None = None,
        since: datetime | None = None,
    ) -> dict[str, float]:
        where: list[str] = []
        params: list = []
        if agent_name:
            where.append("agent_name=?")
            params.append(agent_name)
        if since:
            where.append("ts >= ?")
            params.append(since.isoformat())
        sql = "SELECT context, COALESCE(SUM(cost_usd), 0.0) AS total FROM llm_usage"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY context"
        with self.store.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return {r["context"]: float(r["total"]) for r in rows}
