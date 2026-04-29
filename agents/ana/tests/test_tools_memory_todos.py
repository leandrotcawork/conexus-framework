from unittest.mock import MagicMock

from agents.ana.tools import AnaTools
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


def _make(tmp_db_path, tmp_wiki_dir):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    wiki = WikiStore(tmp_wiki_dir, autocommit=False)
    return AnaTools(store=store, wiki=wiki, calendar=MagicMock())


def test_memory_roundtrip(tmp_db_path, tmp_wiki_dir):
    tools = _make(tmp_db_path, tmp_wiki_dir)
    tools.memory_set("tz", "America/Sao_Paulo")
    assert tools.memory_get("tz") == "America/Sao_Paulo"
    assert any(f["key"] == "tz" for f in tools.memory_list_facts())


def test_todos_lifecycle(tmp_db_path, tmp_wiki_dir):
    tools = _make(tmp_db_path, tmp_wiki_dir)
    r = tools.todos_add("comprar café", due_iso="2026-04-13T10:00:00-03:00")
    assert "id" in r
    open_todos = tools.todos_list("open")
    assert len(open_todos) == 1
    tools.todos_mark_done(r["id"])
    assert tools.todos_list("open") == []
