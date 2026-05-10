from __future__ import annotations

from pathlib import Path

from conexus.core.memory.wiki.lint import lint_wiki
from conexus.core.memory.wiki.local import LocalBackend
from conexus.core.memory.wiki_store import WikiStore as _WikiStore


try:
    from conexus.core.memory.sqlite_store import SqliteStore
    from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex
except ImportError:
    SqliteStore = None
    SqliteFtsIndex = None


class WikiStore:
    def __init__(self, backend: LocalBackend) -> None:
        self.backend = backend


def _make_store(tmp_path: Path):
    backend = LocalBackend(tmp_path / "wiki")

    if SqliteStore is not None and SqliteFtsIndex is not None:
        try:
            sqlite = SqliteStore(":memory:")
            sqlite.init_db()
            return _WikiStore(backend, index=SqliteFtsIndex(store=sqlite, agent_id="a", backend=backend))
        except TypeError:
            pass

    return WikiStore(backend)


def test_orphans_flagged_when_not_referenced_in_index(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.backend.write("index.md", "# Index\n- [linked](linked.md)\n")
    store.backend.write("linked.md", "---\ncreated: 2026-05-09\nupdated: 2026-05-09\n---\nlinked body")
    store.backend.write("orphan.md", "---\ncreated: 2026-05-09\nupdated: 2026-05-09\n---\norphan body")

    report = lint_wiki(store)

    assert "orphan.md" in report.orphans


def test_dead_links_flagged_when_target_missing(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.backend.write(
        "a.md",
        "---\ncreated: 2026-05-09\nupdated: 2026-05-09\n---\nsee [Missing](missing.md#x)",
    )

    report = lint_wiki(store)

    assert ("a.md", "missing.md") in report.dead_links


def test_missing_frontmatter_flagged(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.backend.write("raw.md", "# Raw\nno frontmatter")

    report = lint_wiki(store)

    assert "raw.md" in report.missing_frontmatter


def test_stub_pages_flagged_under_200_chars_excluding_index_and_log(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.backend.write("stub.md", "---\ncreated: 2026-05-09\nupdated: 2026-05-09\n---\nshort")
    store.backend.write("index.md", "# Index\n")
    store.backend.write("log.md", "# Log\n")

    report = lint_wiki(store)

    assert "stub.md" in report.stub_pages
    assert "index.md" not in report.stub_pages
    assert "log.md" not in report.stub_pages


def test_stale_index_flagged_when_index_targets_missing_page(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.backend.write("index.md", "# Index\n- [Missing](missing.md)\n")

    report = lint_wiki(store)

    assert "missing.md" in report.stale_index


def test_clean_report_has_no_issues(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    long_body = "x" * 220
    store.backend.write("index.md", "# Index\n- [Page](page.md)\n")
    store.backend.write("page.md", f"---\ncreated: 2026-05-09\nupdated: 2026-05-09\n---\n{long_body}")

    report = lint_wiki(store)

    assert report.orphans == []
    assert report.dead_links == []
    assert report.missing_frontmatter == []
    assert report.stub_pages == []
    assert report.stale_index == []
    assert report.total_issues == 0
