from datetime import datetime, timedelta, timezone
from pathlib import Path

from conexus.core.llm.usage_tracker import UsageTracker
from conexus.core.memory.sqlite_store import SqliteStore


def _make(tmp_db_path: Path) -> UsageTracker:
    store = SqliteStore(tmp_db_path)
    store.init_db()
    return UsageTracker(store)


def _insert_row(store: SqliteStore, agent_name: str, provider: str, model: str,
                input_tokens: int, output_tokens: int, context: str,
                cost_usd: float, duration_ms: int | None = None, error: str | None = None) -> None:
    """Insert a row directly into the llm_usage table."""
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO llm_usage
               (ts, agent_name, provider, model, input_tokens, output_tokens,
                cost_usd, context, duration_ms, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), agent_name, provider, model,
             input_tokens, output_tokens, cost_usd, context, duration_ms, error),
        )
        conn.commit()


def test_recent_queries_rows(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    tracker = UsageTracker(store)
    _insert_row(store, "ana", "gemini", "gemini-2.0-flash", 1000, 500, "reactive", 0.001, 842)
    rows = tracker.recent(limit=10)
    assert len(rows) == 1
    assert rows[0]["agent_name"] == "ana"
    assert rows[0]["context"] == "reactive"
    assert rows[0]["cost_usd"] == 0.001


def test_total_usd_aggregation(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    tracker = UsageTracker(store)
    for _ in range(3):
        _insert_row(store, "ana", "gemini", "gemini-2.0-flash", 1000, 500, "reactive", 0.001)
    _insert_row(store, "researcher", "gemini", "gemini-2.0-flash", 1000, 500, "briefing", 0.001)

    total_ana = tracker.total_usd(agent_name="ana")
    assert total_ana == 0.003  # 3 rows at 0.001 each

    total_all = tracker.total_usd()
    assert total_all == 0.004  # 4 total rows

    by_ctx = tracker.by_context(agent_name="ana")
    assert by_ctx.get("reactive", 0) == 0.003


def test_total_usd_since(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    tracker = UsageTracker(store)
    _insert_row(store, "ana", "gemini", "gemini-2.0-flash", 1000, 500, "reactive", 0.001)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert tracker.total_usd(agent_name="ana", since=future) == 0.0
