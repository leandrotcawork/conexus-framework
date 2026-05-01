"""Trust-boundary clear must be a logged operator action with reason string."""
from __future__ import annotations
import sqlite3
import pytest
from conexus.core.team.handoff import Handoff
from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation
from conexus.core.trifecta.tags import DataClass


def _h(**kw):
    base = dict(from_agent="a", to_agent="b", payload={})
    base.update(kw)
    return Handoff(**base)


def test_handoff_trust_cleared_is_optional_string():
    h = _h(trust_boundary_cleared="approved-by-leandro-2026-04-30")
    assert h.trust_boundary_cleared == "approved-by-leandro-2026-04-30"


def test_handoff_trust_cleared_default_none():
    h = _h()
    assert h.trust_boundary_cleared is None


def test_guard_from_handoff_passes_reason():
    h = _h(
        tags={DataClass.untrusted_read, DataClass.private_read},
        trust_boundary_cleared="manual-approval-123",
    )
    g = TrifectaGuard.from_handoff({"send_email": "external_write"}, h)
    g.check_and_record("send_email")  # must not raise — trust cleared


def test_guard_no_clear_still_blocks():
    h = _h(tags={DataClass.untrusted_read, DataClass.private_read})
    g = TrifectaGuard.from_handoff({"send_email": "external_write"}, h)
    with pytest.raises(TrifectaViolation):
        g.check_and_record("send_email")


def test_clear_boundary_method_records_reason():
    g = TrifectaGuard({"send_email": "external_write"})
    g._taint.add(DataClass.untrusted_read)
    g._taint.add(DataClass.private_read)
    g.clear_boundary("operator-override-ticket-42")
    assert g._trust_cleared == "operator-override-ticket-42"
    g.check_and_record("send_email")  # no raise


def test_audit_writes_trust_cleared_truthy_when_reason_set(tmp_path):
    from conexus.core.memory.handoff_audit import init_handoff_audit, record_handoff
    db = tmp_path / "audit.db"
    conn = sqlite3.connect(db)
    init_handoff_audit(conn)
    h = _h(trust_boundary_cleared="reason-x")
    record_handoff(conn, h, "routed")
    row = conn.execute("SELECT trust_cleared FROM handoff_audit").fetchone()
    assert row[0] == 1


def test_handoff_legacy_bool_true_coerced_to_sentinel():
    """Replay must accept Phase 8 envelopes with bool True."""
    h = Handoff.model_validate_json(
        '{"schema_version":"1","from_agent":"a","to_agent":"b",'
        '"trust_boundary_cleared":true,"tags":[]}'
    )
    assert h.trust_boundary_cleared == "legacy:phase-8"


def test_handoff_legacy_bool_false_coerced_to_none():
    h = Handoff.model_validate_json(
        '{"schema_version":"1","from_agent":"a","to_agent":"b",'
        '"trust_boundary_cleared":false,"tags":[]}'
    )
    assert h.trust_boundary_cleared is None
