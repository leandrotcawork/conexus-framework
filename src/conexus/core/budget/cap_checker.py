"""Budget cap checker: enforces daily/monthly spending limits per agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from conexus.core.llm.usage_tracker import UsageTracker


@dataclass
class BudgetCap:
    daily_usd: float
    monthly_usd: float
    on_exceed: str  # 'notify' | 'halt'


class CapResult:
    def __init__(self, *, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason


class CapChecker:
    def __init__(self, tracker: UsageTracker):
        self.tracker = tracker

    def check(self, agent_name: str, cap: BudgetCap, tz: ZoneInfo = ZoneInfo("America/Sao_Paulo")) -> CapResult:
        """Return CapResult.allowed=False only if cap.on_exceed == 'halt' and limit crossed."""
        today_start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)

        daily_used = self.tracker.total_usd(agent_name=agent_name, since=today_start)
        monthly_used = self.tracker.total_usd(agent_name=agent_name, since=month_start)

        if daily_used >= cap.daily_usd:
            reason = f"daily cap reached ({daily_used:.4f} / {cap.daily_usd:.4f})"
            return CapResult(allowed=(cap.on_exceed == "notify"), reason=reason)
        if monthly_used >= cap.monthly_usd:
            reason = f"monthly cap reached ({monthly_used:.4f} / {cap.monthly_usd:.4f})"
            return CapResult(allowed=(cap.on_exceed == "notify"), reason=reason)

        return CapResult(allowed=True)
