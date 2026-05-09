from pathlib import Path

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex
from conexus.core.memory.wiki.local import LocalBackend


def _setup(tmp_path: Path):
    store = SqliteStore(str(tmp_path / "t.db"))
    store.init_db()
    backend = LocalBackend(tmp_path / "wiki")
    idx = SqliteFtsIndex(store=store, agent_id="a1", backend=backend)
    return store, backend, idx


def test_reindex_path_inserts_chunks(tmp_path):
    store, backend, idx = _setup(tmp_path)
    backend.write("notes.md", "---\ncreated: 2026-05-09\nupdated: 2026-05-09\nreviewed: false\n---\n# H\nbody alpha\n")
    p = (tmp_path / "wiki" / "notes.md").resolve()
    idx.reindex_path("notes.md", backend.read("notes.md"), p.stat().st_mtime_ns)
    hits = idx.search("alpha")
    assert hits and hits[0].path == "notes.md"
    assert hits[0].header_path == ["# H"]


def test_reconcile_drops_missing(tmp_path):
    store, backend, idx = _setup(tmp_path)
    backend.write("a.md", "# A\nalpha\n")
    p = (tmp_path / "wiki" / "a.md").resolve()
    idx.reindex_path("a.md", backend.read("a.md"), p.stat().st_mtime_ns)
    idx.reconcile({})
    assert idx.search("alpha") == []


def test_reconcile_reindexes_stale(tmp_path):
    store, backend, idx = _setup(tmp_path)
    backend.write("a.md", "# A\nalpha\n")
    p = (tmp_path / "wiki" / "a.md").resolve()
    idx.reindex_path("a.md", backend.read("a.md"), 1)
    backend.write("a.md", "# A\nbeta\n")
    new_mt = p.stat().st_mtime_ns
    idx.reconcile({"a.md": new_mt})
    hits_a = idx.search("alpha")
    hits_b = idx.search("beta")
    assert hits_a == []
    assert hits_b and hits_b[0].path == "a.md"


def test_drop_path(tmp_path):
    store, backend, idx = _setup(tmp_path)
    backend.write("a.md", "# A\nalpha\n")
    p = (tmp_path / "wiki" / "a.md").resolve()
    idx.reindex_path("a.md", backend.read("a.md"), p.stat().st_mtime_ns)
    idx.drop_path("a.md")
    assert idx.search("alpha") == []


def test_page_meta_after_reindex(tmp_path):
    store, backend, idx = _setup(tmp_path)
    backend.write("a.md", "---\ncreated: 2026-05-09\nupdated: 2026-05-09\ntags: [x]\nreviewed: false\n---\n# A\nalpha\n")
    p = (tmp_path / "wiki" / "a.md").resolve()
    idx.reindex_path("a.md", backend.read("a.md"), p.stat().st_mtime_ns)
    meta = idx.page_meta("a.md")
    assert meta is not None
    assert meta.tags == ["x"]
