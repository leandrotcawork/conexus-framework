from pathlib import Path

from core.budget.cap_checker import BudgetCap, CapChecker
from core.llm.usage_tracker import UsageTracker
from core.memory.sqlite_store import SqliteStore


def _setup(tmp_db_path: Path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    tracker = UsageTracker(store)
    return tracker


def test_under_cap_allowed(tmp_db_path):
    tracker = _setup(tmp_db_path)
    checker = CapChecker(tracker)
    cap = BudgetCap(daily_usd=1.0, monthly_usd=10.0, on_exceed="halt")
    assert checker.check("ana", cap).allowed is True


def test_halt_mode_blocks_when_over(tmp_db_path):
    tracker = _setup(tmp_db_path)
    # Burn $0.375 by logging 1M/1M tokens on Gemini Flash
    tracker.log_call(
        agent_name="ana", provider="gemini", model="gemini-2.0-flash",
        input_tokens=1_000_000, output_tokens=1_000_000, context="reactive",
    )
    checker = CapChecker(tracker)
    cap = BudgetCap(daily_usd=0.1, monthly_usd=10.0, on_exceed="halt")
    result = checker.check("ana", cap)
    assert result.allowed is False
    assert "daily cap" in result.reason


def test_notify_mode_allows_even_when_over(tmp_db_path):
    tracker = _setup(tmp_db_path)
    tracker.log_call(
        agent_name="ana", provider="gemini", model="gemini-2.0-flash",
        input_tokens=1_000_000, output_tokens=1_000_000, context="reactive",
    )
    checker = CapChecker(tracker)
    cap = BudgetCap(daily_usd=0.1, monthly_usd=10.0, on_exceed="notify")
    result = checker.check("ana", cap)
    assert result.allowed is True
