from pathlib import Path

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex
from conexus.core.memory.wiki.local import LocalBackend
from conexus.core.memory.wiki_store import WikiStore


def _make(tmp_path: Path) -> WikiStore:
    store = SqliteStore(str(tmp_path / "t.db"))
    store.init_db()
    backend = LocalBackend(tmp_path / "wiki")
    idx = SqliteFtsIndex(store=store, agent_id="a", backend=backend)
    return WikiStore(backend, index=idx)


def test_write_injects_frontmatter_and_indexes(tmp_path: Path) -> None:
    ws = _make(tmp_path)
    out = ws.write("a.md", "# Hello\nworld alpha")
    assert out["ok"] is True
    raw = ws.read("a.md")
    assert raw.startswith("---\n")
    hits = ws.search("alpha")
    assert hits and hits[0]["path"] == "a.md"


def test_search_after_external_modification(tmp_path: Path) -> None:
    ws = _make(tmp_path)
    ws.write("a.md", "# A\nfoo")
    (tmp_path / "wiki" / "a.md").write_text(
        "---\ncreated: 2026-05-09\nupdated: 2026-05-09\nreviewed: false\n---\n# A\nbar\n",
        encoding="utf-8",
    )
    hits_foo = ws.search("foo")
    hits_bar = ws.search("bar")
    assert hits_foo == []
    assert hits_bar and hits_bar[0]["path"] == "a.md"


def test_delete_drops_from_index(tmp_path: Path) -> None:
    ws = _make(tmp_path)
    ws.write("a.md", "# A\nalpha")
    ws.delete("a.md")
    assert ws.search("alpha") == []


def test_exists(tmp_path: Path) -> None:
    ws = _make(tmp_path)
    assert ws.exists("a.md") is False
    ws.write("a.md", "# A\nbody")
    assert ws.exists("a.md") is True


def test_move_with_backlink_update(tmp_path: Path) -> None:
    ws = _make(tmp_path)
    ws.write("target.md", "# T\ncontent")
    ws.write("ref.md", "# R\nsee [target.md#t] for details")
    res = ws.move("target.md", "renamed.md")
    assert res["ok"] is True
    assert res["backlinks_updated"] == 1
    assert "renamed.md" in ws.read("ref.md")


def test_legacy_no_index(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / "wiki")
    ws = WikiStore(backend)
    ws.write("a.md", "# A\nalpha")
    hits = ws.search("alpha")
    assert hits and hits[0]["path"] == "a.md"
