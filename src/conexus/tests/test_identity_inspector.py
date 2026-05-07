"""Test the identity tools inspector."""
from conexus.web.admin.services.identity_inspector import list_identity_tools


def test_returns_12_when_enabled():
    tools = list_identity_tools(enabled=True)
    names = {t.name for t in tools}
    assert {"memory_get", "memory_set", "wiki_read", "block_set"} <= names
    assert len(tools) == 12


def test_returns_empty_when_disabled():
    assert list_identity_tools(enabled=False) == []
