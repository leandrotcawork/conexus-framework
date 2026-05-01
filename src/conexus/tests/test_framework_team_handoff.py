import pytest
from conexus.core.team.handoff import Handoff
from conexus.core.trifecta.tags import DataClass


def test_handoff_default_shape():
    h = Handoff(from_agent="ana", to_agent="pm", payload={"task": "design"})
    assert h.schema_version == "1"
    assert h.context_mode == "summary"
    assert h.return_on is None
    assert h.hop_count == 0
    assert h.max_hops == 5
    assert h.tags == set()
    assert h.trust_boundary_cleared is None


def test_handoff_carries_taint():
    h = Handoff(
        from_agent="researcher",
        to_agent="pm",
        payload={"summary": "..."},
        tags={DataClass.untrusted_read, DataClass.private_read},
    )
    assert DataClass.untrusted_read in h.tags
    assert DataClass.private_read in h.tags


def test_handoff_max_hops_enforced_at_increment():
    h = Handoff(from_agent="a", to_agent="b", payload={}, hop_count=4, max_hops=5)
    h2 = h.next_hop("c")
    assert h2.hop_count == 5
    with pytest.raises(ValueError, match="max_hops"):
        h2.next_hop("d")


def test_handoff_json_roundtrip():
    h = Handoff(from_agent="a", to_agent="b", payload={"x": 1}, tags={DataClass.untrusted_read})
    s = h.model_dump_json()
    h2 = Handoff.model_validate_json(s)
    assert h2 == h
