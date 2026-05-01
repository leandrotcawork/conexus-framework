import pytest
from conexus.core.team.handoff import Handoff
from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation
from conexus.core.trifecta.tags import DataClass


def test_guard_seeded_taint_blocks_immediately():
    guard = TrifectaGuard(
        tool_tags={"wiki_write": "external_write"},
        seed_taint={DataClass.untrusted_read, DataClass.private_read},
    )
    with pytest.raises(TrifectaViolation):
        guard.check_and_record("wiki_write")


def test_guard_trust_boundary_cleared_bypasses_seed():
    guard = TrifectaGuard(
        tool_tags={"wiki_write": "external_write"},
        seed_taint={DataClass.untrusted_read, DataClass.private_read},
        trust_boundary_cleared=True,
    )
    guard.check_and_record("wiki_write")  # no raise


def test_handoff_seeds_guard_constructor():
    h = Handoff(
        from_agent="researcher",
        to_agent="pm",
        payload={},
        tags={DataClass.untrusted_read, DataClass.private_read},
    )
    guard = TrifectaGuard.from_handoff({"wiki_write": "external_write"}, h)
    with pytest.raises(TrifectaViolation):
        guard.check_and_record("wiki_write")
