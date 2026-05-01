"""BudgetCascader — enforces team pool + per-member shares with 3 policies.

Spec: docs/superpowers/specs/2026-04-29-conexus-framework-v2.md §1.5, §1.9.
"""
from __future__ import annotations
from enum import Enum


class BudgetPolicy(str, Enum):
    notify = "notify"
    halt_member = "halt_member"
    borrow_from_pool = "borrow_from_pool"


class ShareExceeded(RuntimeError):
    pass


class BudgetCascader:
    def __init__(self, team_daily_usd: float, shares: dict[str, float], policy: BudgetPolicy) -> None:
        self._pool = team_daily_usd
        self._shares = shares
        self._policy = policy
        self._spent: dict[str, float] = {m: 0.0 for m in shares}
        self._halted: set[str] = set()

    def spent(self, member: str) -> float:
        return self._spent.get(member, 0.0)

    def pool_remaining(self) -> float:
        return self._pool - sum(self._spent.values())

    def check_and_debit(self, member: str, cost: float) -> bool:
        if member in self._halted:
            raise ShareExceeded(f"{member} halted")
        share = self._shares.get(member, 0.0) * self._pool
        new_spent = self._spent.get(member, 0.0) + cost
        if new_spent <= share:
            self._spent[member] = new_spent
            return True
        if self._policy == BudgetPolicy.notify:
            return False
        if self._policy == BudgetPolicy.halt_member:
            self._halted.add(member)
            return False
        if self._policy == BudgetPolicy.borrow_from_pool:
            if self.pool_remaining() >= cost:
                self._spent[member] = new_spent
                return True
            return False
        raise ValueError(f"unknown policy: {self._policy}")
