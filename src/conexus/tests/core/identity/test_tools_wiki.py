from __future__ import annotations

from unittest.mock import Mock, patch

from conexus.core.identity.blocks import BlockStore
from conexus.core.identity.tools import IdentityTools
from conexus.core.memory.sqlite_store import SqliteStore


def _make_tools(tmp_path):
    store = SqliteStore(":memory:")
    store.init_db()
    blocks = BlockStore(store)
    return IdentityTools(
        agent_id="ana",
        store=store,
        wiki=None,
        blocks=blocks,
        block_specs={"user": 500, "scratch": 200},
    )


def test_wiki_delete_returns_deleted_bool(tmp_path, monkeypatch):
    tools = _make_tools(tmp_path)
    wiki = Mock()
    monkeypatch.setattr(tools, "_require_wiki", lambda: wiki)

    assert tools.wiki_delete(path="notes/a.md") == {"ok": True, "deleted": True}
    wiki.delete.assert_called_once_with("notes/a.md")


def test_wiki_exists_returns_bool(tmp_path, monkeypatch):
    tools = _make_tools(tmp_path)
    wiki = Mock()
    wiki.exists.return_value = True
    monkeypatch.setattr(tools, "_require_wiki", lambda: wiki)

    assert tools.wiki_exists(path="notes/a.md") is True
    wiki.exists.assert_called_once_with("notes/a.md")


def test_wiki_move_returns_mapping_with_backlinks(tmp_path, monkeypatch):
    tools = _make_tools(tmp_path)
    wiki = Mock()
    wiki.move.return_value = {"moved": "a.md", "to": "archive/a.md", "backlinks_updated": 3}
    monkeypatch.setattr(tools, "_require_wiki", lambda: wiki)

    result = tools.wiki_move(src="a.md", dst="archive/a.md")
    assert result == {"ok": True, "moved": "a.md", "to": "archive/a.md", "backlinks_updated": 3}
    wiki.move.assert_called_once_with("a.md", "archive/a.md")


def test_wiki_lint_serializes_dead_links(tmp_path, monkeypatch):
    tools = _make_tools(tmp_path)
    wiki = Mock()
    monkeypatch.setattr(tools, "_require_wiki", lambda: wiki)

    from conexus.core.memory.wiki.lint import LintReport
    report = LintReport(
        dead_links=[("a.md", "missing.md"), ("b.md", "ghost.md")],
        orphans=["orphan.md"],
        missing_frontmatter=[],
        stub_pages=[],
        stale_index=[],
    )

    with patch("conexus.core.identity.tools.lint_wiki", return_value=report) as mock_lint:
        result = tools.wiki_lint()

    mock_lint.assert_called_once_with(wiki)
    assert result == {
        "dead_links": [["a.md", "missing.md"], ["b.md", "ghost.md"]],
        "orphans": ["orphan.md"],
        "missing_frontmatter": [],
        "stub_pages": [],
        "stale_index": [],
    }


def test_wiki_index_update_returns_ok(tmp_path, monkeypatch):
    tools = _make_tools(tmp_path)
    wiki = Mock()
    monkeypatch.setattr(tools, "_require_wiki", lambda: wiki)

    assert tools.wiki_index_update(path="a.md", summary="summary") == {"ok": True}
    wiki.update_index.assert_called_once_with("a.md", "summary")
