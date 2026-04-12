from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.llm.usage_tracker import UsageTracker
from core.memory.sqlite_store import SqliteStore


def _make(tmp_db_path: Path) -> UsageTracker:
    store = SqliteStore(tmp_db_path)
    store.init_db()
    return UsageTracker(store)


def test_log_call_writes_row(tmp_db_path):
    tracker = _make(tmp_db_path)
    tracker.log_call(
        agent_name="ana",
        provider="gemini",
        model="gemini-2.0-flash",
        input_tokens=1000,
        output_tokens=500,
        context="reactive",
        duration_ms=842,
    )
    rows = tracker.recent(limit=10)
    assert len(rows) == 1
    assert rows[0]["agent_name"] == "ana"
    assert rows[0]["context"] == "reactive"
    assert rows[0]["cost_usd"] > 0


def test_total_usd_aggregation(tmp_db_path):
    tracker = _make(tmp_db_path)
    for _ in range(3):
        tracker.log_call(
            agent_name="ana",
            provider="gemini",
            model="gemini-2.0-flash",
            input_tokens=1000,
            output_tokens=500,
            context="reactive",
        )
    tracker.log_call(
        agent_name="researcher",
        provider="gemini",
        model="gemini-2.0-flash",
        input_tokens=1000,
        output_tokens=500,
        context="briefing",
    )

    total_ana = tracker.total_usd(agent_name="ana")
    assert total_ana > 0

    total_all = tracker.total_usd()
    assert total_all > total_ana  # researcher added

    by_ctx = tracker.by_context(agent_name="ana")
    assert by_ctx.get("reactive", 0) > 0


def test_total_usd_since(tmp_db_path):
    tracker = _make(tmp_db_path)
    tracker.log_call(
        agent_name="ana", provider="gemini", model="gemini-2.0-flash",
        input_tokens=1000, output_tokens=500, context="reactive",
    )
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert tracker.total_usd(agent_name="ana", since=future) == 0.0
