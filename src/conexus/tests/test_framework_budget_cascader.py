import pytest
from conexus.core.team.budget_cascader import BudgetCascader, BudgetPolicy, ShareExceeded


def _shares():
    return {"ana": 0.2, "pm": 0.4, "researcher": 0.4}


def test_cascader_within_share_allows():
    c = BudgetCascader(team_daily_usd=1.0, shares=_shares(), policy=BudgetPolicy.notify)
    assert c.check_and_debit("ana", 0.10) is True
    assert c.spent("ana") == pytest.approx(0.10)


def test_cascader_share_exceeded_notify_blocks():
    c = BudgetCascader(team_daily_usd=1.0, shares=_shares(), policy=BudgetPolicy.notify)
    assert c.check_and_debit("ana", 0.30) is False
    assert c.spent("ana") == 0.0


def test_cascader_share_exceeded_halt_member():
    c = BudgetCascader(team_daily_usd=1.0, shares=_shares(), policy=BudgetPolicy.halt_member)
    assert c.check_and_debit("ana", 0.30) is False
    with pytest.raises(ShareExceeded):
        c.check_and_debit("ana", 0.05)


def test_cascader_borrow_from_pool():
    c = BudgetCascader(team_daily_usd=1.0, shares=_shares(), policy=BudgetPolicy.borrow_from_pool)
    assert c.check_and_debit("ana", 0.30) is True
    assert c.spent("ana") == pytest.approx(0.30)
    assert c.pool_remaining() == pytest.approx(0.70)
    assert c.check_and_debit("pm", 0.40) is True


def test_cascader_pool_exhausted():
    c = BudgetCascader(team_daily_usd=1.0, shares=_shares(), policy=BudgetPolicy.borrow_from_pool)
    c.check_and_debit("ana", 0.20)
    c.check_and_debit("pm", 0.40)
    c.check_and_debit("researcher", 0.40)
    assert c.check_and_debit("ana", 0.01) is False
