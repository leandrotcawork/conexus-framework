"""UsageTracker query-only regression."""
from datetime import datetime, timezone
from conexus.core.llm.usage_tracker import UsageTracker
from conexus.core.memory.sqlite_store import SqliteStore


def test_recent_returns_rows_after_direct_insert(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db"))
    store.init_db()
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO llm_usage
               (ts, agent_name, provider, model, input_tokens, output_tokens,
                cost_usd, context, duration_ms, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), "ana", "deepseek",
             "deepseek-v4-flash", 10, 5, 0.001, "", 100, None),
        )
        conn.commit()
    tracker = UsageTracker(store)
    rows = tracker.recent(agent_name="ana", limit=10)
    assert len(rows) == 1
    assert rows[0]["agent_name"] == "ana"
    assert rows[0]["cost_usd"] == 0.001


def test_log_call_method_removed():
    assert not hasattr(UsageTracker, "log_call")
