from unittest.mock import MagicMock

from agents.ana.tools import AnaTools
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


def _make(tmp_db_path, tmp_wiki_dir):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    wiki = WikiStore(tmp_wiki_dir, autocommit=False)
    return AnaTools(store=store, wiki=wiki, calendar=MagicMock())


def test_wiki_write_read_list(tmp_db_path, tmp_wiki_dir):
    tools = _make(tmp_db_path, tmp_wiki_dir)
    tools.wiki_write("about/leandro.md", "# Leandro\n\nBrazilian founder.")
    assert "Brazilian founder" in tools.wiki_read("about/leandro.md")
    assert "about/leandro.md" in tools.wiki_list("about")


def test_wiki_log_and_index(tmp_db_path, tmp_wiki_dir):
    tools = _make(tmp_db_path, tmp_wiki_dir)
    tools.wiki_append_log("ingest", "Test entry", "Body of entry")
    assert "Test entry" in tools.wiki_read("log.md")
    tools.wiki_update_index("about/leandro.md", "Profile")
    assert "about/leandro.md" in tools.wiki_read("index.md")


def test_wiki_search(tmp_db_path, tmp_wiki_dir):
    tools = _make(tmp_db_path, tmp_wiki_dir)
    tools.wiki_write("projects/conexus.md", "Conexus is an agent framework")
    hits = tools.wiki_search("Conexus")
    assert any(h["path"] == "projects/conexus.md" for h in hits)
