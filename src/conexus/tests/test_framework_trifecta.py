import pytest
from conexus.core.trifecta.tags import DataClass, auto_tag

def test_auto_tag_untrusted_read():
    assert auto_tag("web_fetch") == DataClass.untrusted_read
    assert auto_tag("web_search") == DataClass.untrusted_read

def test_auto_tag_private_read():
    assert auto_tag("wiki_read") == DataClass.private_read
    assert auto_tag("wiki_search") == DataClass.private_read
    assert auto_tag("memory_get") == DataClass.private_read
    assert auto_tag("calendar_list_events") == DataClass.private_read

def test_auto_tag_external_write():
    assert auto_tag("wiki_write") == DataClass.external_write
    assert auto_tag("wiki_append_log") == DataClass.external_write
    assert auto_tag("calendar_create_event") == DataClass.external_write
    assert auto_tag("todos_add") == DataClass.external_write
    assert auto_tag("send_telegram") == DataClass.external_write

def test_auto_tag_returns_none_for_unknown():
    assert auto_tag("compute_hash") is None
    assert auto_tag("format_date") is None


from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation


def _guard(extra: dict | None = None) -> TrifectaGuard:
    tags = {
        "web_fetch": "untrusted_read",
        "wiki_read": "private_read",
        "wiki_write": "external_write",
        "compute_hash": "safe",
    }
    if extra:
        tags.update(extra)
    return TrifectaGuard(tags)

def test_guard_allows_read_sequence():
    g = _guard()
    g.check_and_record("web_fetch")   # untrusted_read
    g.check_and_record("wiki_read")   # private_read — allowed (no write yet)

def test_guard_blocks_exfil():
    g = _guard()
    g.check_and_record("web_fetch")   # untrusted_read
    g.check_and_record("wiki_read")   # private_read
    with pytest.raises(TrifectaViolation, match="blocked"):
        g.check_and_record("wiki_write")  # external_write — BLOCKED

def test_guard_allows_write_without_both_reads():
    g = _guard()
    g.check_and_record("web_fetch")   # untrusted_read only — write still allowed
    g.check_and_record("wiki_write")  # OK: no private_read in taint yet

def test_guard_trust_boundary_cleared():
    g = TrifectaGuard(
        {"web_fetch": "untrusted_read", "wiki_read": "private_read", "wiki_write": "external_write"},
        trust_boundary_cleared=True,
    )
    g.check_and_record("web_fetch")
    g.check_and_record("wiki_read")
    g.check_and_record("wiki_write")  # allowed: trust cleared

def test_guard_untagged_tool_raises():
    g = TrifectaGuard({})  # no tags, no heuristic match
    with pytest.raises(ValueError, match="no data_class tag"):
        g.check_and_record("mystery_tool")

def test_guard_auto_tags_unregistered_tool():
    g = TrifectaGuard({})  # empty explicit tags
    # web_fetch matches auto_tag heuristic
    tag = g.check_and_record("web_fetch")
    from conexus.core.trifecta.tags import DataClass
    assert tag == DataClass.untrusted_read
