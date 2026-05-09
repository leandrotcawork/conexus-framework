from pathlib import Path

from conexus.cli.wiki_migrate import migrate_agent_wiki
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.local import LocalBackend


def test_migrate_injects_frontmatter_and_indexes(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "a.md").write_text("# A\nalpha\n")
    (wiki / "b.md").write_text("---\ncreated: 2025-01-01\nupdated: 2025-01-01\nreviewed: false\n---\n# B\nbeta\n")
    store = SqliteStore(str(tmp_path / "t.db")); store.init_db()
    backend = LocalBackend(wiki)
    result = migrate_agent_wiki(agent_id="a", backend=backend, store=store)
    assert result["pages_processed"] == 2
    assert result["frontmatter_injected"] == 1
    a_meta = store.wiki_page_get("a", "a.md")
    assert a_meta["created"] is not None


def test_migrate_idempotent(tmp_path):
    wiki = tmp_path / "wiki"; wiki.mkdir()
    (wiki / "a.md").write_text("# A\nbody\n")
    store = SqliteStore(str(tmp_path / "t.db")); store.init_db()
    backend = LocalBackend(wiki)
    r1 = migrate_agent_wiki("a", backend, store)
    r2 = migrate_agent_wiki("a", backend, store)
    assert r1["frontmatter_injected"] == 1
    assert r2["frontmatter_injected"] == 0
