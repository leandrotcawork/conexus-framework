from pathlib import Path

import pytest

from conexus.core.memory.wiki_store import WikiStore


def test_write_and_read(tmp_wiki_dir: Path):
    store = WikiStore.local(tmp_wiki_dir)
    store.write("about/leandro.md", "# Leandro\n\nBrazilian founder.")
    assert store.read("about/leandro.md") == "# Leandro\n\nBrazilian founder."


def test_list_files(tmp_wiki_dir: Path):
    store = WikiStore.local(tmp_wiki_dir)
    store.write("about/leandro.md", "a")
    store.write("about/conexus.md", "b")
    store.write("preferences/schedule.md", "c")

    about = sorted(store.list("about"))
    assert about == ["about/conexus.md", "about/leandro.md"]

    all_files = sorted(store.list())
    assert all_files == [
        "about/conexus.md",
        "about/leandro.md",
        "preferences/schedule.md",
    ]


def test_search_full_text(tmp_wiki_dir: Path):
    store = WikiStore.local(tmp_wiki_dir)
    store.write("about/leandro.md", "Leandro is building Conexus")
    store.write("about/conexus.md", "Conexus is a personal agent framework")
    store.write("preferences/schedule.md", "No meetings Monday morning")

    results = store.search("Conexus")
    paths = {r["path"] for r in results}
    assert paths == {"about/leandro.md", "about/conexus.md"}


def test_reject_path_escape(tmp_wiki_dir: Path):
    store = WikiStore.local(tmp_wiki_dir)
    with pytest.raises(ValueError):
        store.write("../outside.md", "evil")
    with pytest.raises(ValueError):
        store.read("../../etc/passwd")


def test_append_log_format(tmp_wiki_dir: Path):
    store = WikiStore.local(tmp_wiki_dir)
    store.append_log("ingest", "Leandro hates Mondays", "Updated preferences/schedule.md")
    log = store.read("log.md")
    assert "## [" in log
    assert "ingest | Leandro hates Mondays" in log
    assert "Updated preferences/schedule.md" in log

    # Second append adds a new entry
    store.append_log("recap", "Evening recap delivered", "3 events, 2 todos")
    log = store.read("log.md")
    assert log.count("## [") == 2


def test_update_index_upsert(tmp_wiki_dir: Path):
    store = WikiStore.local(tmp_wiki_dir)
    store.update_index("about/leandro.md", "Profile, focus, current projects")
    idx = store.read("index.md")
    assert "[leandro](about/leandro.md)" in idx
    assert "Profile, focus, current projects" in idx

    # Updating the same path replaces the existing line
    store.update_index("about/leandro.md", "Updated profile")
    idx = store.read("index.md")
    assert idx.count("about/leandro.md") == 1
    assert "Updated profile" in idx


def test_wikistore_accepts_path_via_local_classmethod(tmp_path):
    from conexus.core.memory.wiki_store import WikiStore
    store = WikiStore.local(tmp_path)
    store.write("a.md", "x")
    assert store.read("a.md") == "x"


def test_wikistore_accepts_backend_directly(tmp_path):
    from conexus.core.memory.wiki import LocalBackend
    from conexus.core.memory.wiki_store import WikiStore
    store = WikiStore(LocalBackend(tmp_path))
    store.write("a.md", "y")
    assert store.list() == ["a.md"]


def test_wikistore_legacy_path_constructor_still_works(tmp_path):
    """Back-compat: passing a path builds LocalBackend internally."""
    from conexus.core.memory.wiki_store import WikiStore
    store = WikiStore(str(tmp_path))
    store.write("a.md", "z")
    assert store.read("a.md") == "z"
