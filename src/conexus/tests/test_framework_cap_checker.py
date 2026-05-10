from datetime import datetime, timezone
from pathlib import Path

from conexus.core.budget.cap_checker import BudgetCap, CapChecker
from conexus.core.llm.usage_tracker import UsageTracker
from conexus.core.memory.sqlite_store import SqliteStore


def _setup(tmp_db_path: Path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    tracker = UsageTracker(store)
    return store, tracker


def _insert_row(store: SqliteStore, agent_name: str, provider: str, model: str,
                input_tokens: int, output_tokens: int, cost_usd: float,
                context: str = "reactive") -> None:
    """Insert a row directly into the llm_usage table."""
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO llm_usage
               (ts, agent_name, provider, model, input_tokens, output_tokens,
                cost_usd, context, duration_ms, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), agent_name, provider, model,
             input_tokens, output_tokens, cost_usd, context, None, None),
        )
        conn.commit()


def test_under_cap_allowed(tmp_db_path):
    store, tracker = _setup(tmp_db_path)
    checker = CapChecker(tracker)
    cap = BudgetCap(daily_usd=1.0, monthly_usd=10.0, on_exceed="halt")
    assert checker.check("ana", cap).allowed is True


def test_halt_mode_blocks_when_over(tmp_db_path):
    store, tracker = _setup(tmp_db_path)
    # Burn $0.375 by logging 1M/1M tokens on Gemini Flash
    _insert_row(store, "ana", "gemini", "gemini-2.0-flash",
                input_tokens=1_000_000, output_tokens=1_000_000, cost_usd=0.375)
    checker = CapChecker(tracker)
    cap = BudgetCap(daily_usd=0.1, monthly_usd=10.0, on_exceed="halt")
    result = checker.check("ana", cap)
    assert result.allowed is False
    assert "daily cap" in result.reason


def test_notify_mode_allows_even_when_over(tmp_db_path):
    store, tracker = _setup(tmp_db_path)
    _insert_row(store, "ana", "gemini", "gemini-2.0-flash",
                input_tokens=1_000_000, output_tokens=1_000_000, cost_usd=0.375)
    checker = CapChecker(tracker)
    cap = BudgetCap(daily_usd=0.1, monthly_usd=10.0, on_exceed="notify")
    result = checker.check("ana", cap)
    assert result.allowed is True
