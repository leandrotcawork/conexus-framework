from pathlib import Path

from conexus.core.memory.sqlite_store import SqliteStore


def _store(tmp_path: Path) -> SqliteStore:
    s = SqliteStore(str(tmp_path / "test.db"))
    s.init_db()
    return s


def test_wiki_pages_table_exists(tmp_path):
    s = _store(tmp_path)
    with s.conn as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wiki_pages'").fetchall()
    assert rows


def test_wiki_chunks_fts_exists(tmp_path):
    s = _store(tmp_path)
    with s.conn as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE name='wiki_chunks_fts'").fetchall()
    assert rows


def test_wiki_page_upsert_get(tmp_path):
    s = _store(tmp_path)
    s.wiki_page_set(
        "agent1",
        "notes.md",
        mtime_ns=123,
        created="2026-05-09",
        updated="2026-05-09",
        tags=["a"],
        source="test",
        reviewed=False,
    )
    row = s.wiki_page_get("agent1", "notes.md")
    assert row["mtime_ns"] == 123
    assert row["tags"] == ["a"]
    assert row["reviewed"] is False


def test_wiki_page_delete_cascades_chunks(tmp_path):
    s = _store(tmp_path)
    s.wiki_page_set(
        "agent1",
        "n.md",
        mtime_ns=1,
        created=None,
        updated=None,
        tags=[],
        source=None,
        reviewed=False,
    )
    s.wiki_chunk_insert(
        "agent1",
        "n.md",
        header_path=["# H"],
        line_start=1,
        line_end=2,
        body="hello world",
    )
    s.wiki_page_delete("agent1", "n.md")
    with s.conn as c:
        chunks = c.execute("SELECT * FROM wiki_chunks WHERE path='n.md'").fetchall()
    assert chunks == []


def test_fts_search_round_trip(tmp_path):
    s = _store(tmp_path)
    s.wiki_page_set(
        "agent1",
        "n.md",
        mtime_ns=1,
        created=None,
        updated=None,
        tags=[],
        source=None,
        reviewed=False,
    )
    s.wiki_chunk_insert(
        "agent1",
        "n.md",
        header_path=["# H"],
        line_start=1,
        line_end=2,
        body="alpha beta gamma",
    )
    hits = s.wiki_fts_search("agent1", "beta", k=5)
    assert len(hits) == 1
    assert hits[0]["path"] == "n.md"


def test_fts_diacritic_insensitive(tmp_path):
    s = _store(tmp_path)
    s.wiki_page_set(
        "agent1",
        "n.md",
        mtime_ns=1,
        created=None,
        updated=None,
        tags=[],
        source=None,
        reviewed=False,
    )
    s.wiki_chunk_insert(
        "agent1",
        "n.md",
        header_path=["# H"],
        line_start=1,
        line_end=2,
        body="café com leite",
    )
    assert len(s.wiki_fts_search("agent1", "cafe", k=5)) == 1


def test_per_agent_isolation(tmp_path):
    s = _store(tmp_path)
    for a in ("a1", "a2"):
        s.wiki_page_set(
            a,
            "n.md",
            mtime_ns=1,
            created=None,
            updated=None,
            tags=[],
            source=None,
            reviewed=False,
        )
        s.wiki_chunk_insert(
            a,
            "n.md",
            header_path=["# H"],
            line_start=1,
            line_end=2,
            body=f"hello from {a}",
        )
    a1_hits = s.wiki_fts_search("a1", "hello", k=5)
    assert len(a1_hits) == 1 and "a1" in a1_hits[0]["snippet"]
