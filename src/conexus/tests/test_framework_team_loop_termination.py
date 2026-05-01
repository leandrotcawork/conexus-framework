"""max_parallel_members + termination_text loop wiring."""
from __future__ import annotations
import pytest
from conexus.core.team.team_pack import TeamPolicy


def test_team_policy_default_max_parallel_members_is_one():
    p = TeamPolicy()
    assert p.max_parallel_members == 1


def test_team_policy_accepts_override():
    p = TeamPolicy(max_parallel_members=3)
    assert p.max_parallel_members == 3


def test_team_policy_rejects_zero_max_parallel():
    with pytest.raises(Exception):  # pydantic ValidationError
        TeamPolicy(max_parallel_members=0)
