import pytest
from conexus.core.memory.wiki.frontmatter import parse, inject, validate

def test_parse_no_frontmatter():
    meta, body = parse("# Hello\nworld")
    assert meta == {}
    assert body == "# Hello\nworld"

def test_parse_valid_frontmatter():
    text = "---\ncreated: 2026-05-09\ntags: [wiki]\nreviewed: false\n---\n# Body\n"
    meta, body = parse(text)
    assert meta["created"] == "2026-05-09"
    assert meta["tags"] == ["wiki"]
    assert meta["reviewed"] is False
    assert body == "# Body\n"

def test_parse_malformed_yaml_raises():
    with pytest.raises(ValueError):
        parse("---\n: : :\n---\nbody")

def test_inject_adds_when_missing():
    out = inject("# Body\n", {"created": "2026-05-09", "updated": "2026-05-09",
                               "tags": [], "source": "manual", "reviewed": False})
    meta, body = parse(out)
    assert meta["created"] == "2026-05-09"
    assert body == "# Body\n"

def test_inject_updates_updated_only():
    text = "---\ncreated: 2026-01-01\nupdated: 2026-01-01\nreviewed: true\n---\n# Body\n"
    out = inject(text, {"created": "ignored", "updated": "2026-05-09",
                        "tags": [], "source": "manual", "reviewed": False})
    meta, _ = parse(out)
    assert meta["created"] == "2026-01-01"
    assert meta["updated"] == "2026-05-09"
    assert meta["reviewed"] is True

def test_validate_warns_missing_optional():
    warnings = validate({"created": "2026-05-09", "updated": "2026-05-09"})
    assert any("source" in w or "tags" in w for w in warnings)

def test_validate_hard_error_on_bad_reviewed():
    with pytest.raises(ValueError):
        validate({"created": "2026-05-09", "updated": "2026-05-09", "reviewed": "yes"})

def test_validate_hard_error_on_bad_date():
    with pytest.raises(ValueError):
        validate({"created": "yesterday", "updated": "2026-05-09", "reviewed": False})
