from __future__ import annotations

from collections import namedtuple
from unittest.mock import Mock

from conexus.core.identity.blocks import BlockStore
from conexus.core.identity.tools import IdentityTools
from conexus.core.memory.sqlite_store import SqliteStore


class _DummyReport:
    def __init__(self, dead_links, warnings):
        self.dead_links = dead_links
        self.warnings = warnings


def _make_tools(tmp_path):
    store = SqliteStore(str(tmp_path / "id.db"))
    store.init_db()
    blocks = BlockStore(store)
    return IdentityTools(
        agent_id="ana",
        store=store,
        wiki=None,
        blocks=blocks,
        block_specs={"user": 500, "scratch": 200},
    )


def test_wiki_delete_returns_deleted_path(tmp_path, monkeypatch):
    tools = _make_tools(tmp_path)
    wiki = Mock()
    monkeypatch.setattr(tools, "_require_wiki", lambda: wiki)

    assert tools.wiki_delete(path="notes/a.md") == {"deleted": "notes/a.md"}
    wiki.delete.assert_called_once_with("notes/a.md")


def test_wiki_exists_returns_bool(tmp_path, monkeypatch):
    tools = _make_tools(tmp_path)
    wiki = Mock()
    wiki.exists.return_value = True
    monkeypatch.setattr(tools, "_require_wiki", lambda: wiki)

    assert tools.wiki_exists(path="notes/a.md") is True
    wiki.exists.assert_called_once_with("notes/a.md")


def test_wiki_move_returns_mapping(tmp_path, monkeypatch):
    tools = _make_tools(tmp_path)
    wiki = Mock()
    monkeypatch.setattr(tools, "_require_wiki", lambda: wiki)

    assert tools.wiki_move(src="a.md", dst="archive/a.md") == {"moved": "a.md", "to": "archive/a.md"}
    wiki.move.assert_called_once_with("a.md", "archive/a.md")


def test_wiki_lint_serializes_dead_links(tmp_path, monkeypatch):
    tools = _make_tools(tmp_path)
    wiki = Mock()
    DeadLink = namedtuple("DeadLink", ["source", "target"])
    wiki.lint.return_value = _DummyReport(
        dead_links=[("a.md", "missing.md"), DeadLink("b.md", "ghost.md")],
        warnings=["orphan index entry"],
    )
    monkeypatch.setattr(tools, "_require_wiki", lambda: wiki)

    assert tools.wiki_lint() == {
        "dead_links": [["a.md", "missing.md"], ["b.md", "ghost.md"]],
        "warnings": ["orphan index entry"],
    }
    wiki.lint.assert_called_once_with()


def test_wiki_index_update_returns_indexed_path(tmp_path, monkeypatch):
    tools = _make_tools(tmp_path)
    wiki = Mock()
    monkeypatch.setattr(tools, "_require_wiki", lambda: wiki)

    assert tools.wiki_index_update(path="a.md", summary="summary") == {"indexed": "a.md"}
    wiki.index_update.assert_called_once_with("a.md", "summary")
