"""LocalBackend: filesystem wiki ops + path safety."""
from __future__ import annotations

import pytest

from conexus.core.memory.wiki import LocalBackend


def test_write_then_read_roundtrip(tmp_path):
    b = LocalBackend(tmp_path)
    b.write("note.md", "hello")
    assert b.read("note.md") == "hello"


def test_list_returns_relative_posix_paths(tmp_path):
    b = LocalBackend(tmp_path)
    b.write("a.md", "x")
    b.write("sub/b.md", "y")
    assert sorted(b.list()) == ["a.md", "sub/b.md"]


def test_list_folder_filters(tmp_path):
    b = LocalBackend(tmp_path)
    b.write("a.md", "x")
    b.write("sub/b.md", "y")
    assert b.list("sub") == ["sub/b.md"]


def test_search_returns_snippets(tmp_path):
    b = LocalBackend(tmp_path)
    b.write("note.md", "the quick brown fox jumps over the lazy dog")
    hits = b.search("brown")
    assert len(hits) == 1
    assert hits[0]["path"] == "note.md"
    assert "brown" in hits[0]["snippet"]


def test_exists_and_delete(tmp_path):
    b = LocalBackend(tmp_path)
    b.write("x.md", "v")
    assert b.exists("x.md")
    b.delete("x.md")
    assert not b.exists("x.md")


def test_read_missing_raises(tmp_path):
    b = LocalBackend(tmp_path)
    with pytest.raises(FileNotFoundError):
        b.read("ghost.md")


def test_path_traversal_rejected(tmp_path):
    b = LocalBackend(tmp_path)
    with pytest.raises(ValueError):
        b.write("../escape.md", "x")
    with pytest.raises(ValueError):
        b.read("../../../etc/passwd")


def test_absolute_path_rejected(tmp_path):
    b = LocalBackend(tmp_path)
    with pytest.raises(ValueError):
        b.write("/abs/path.md", "x")


def test_root_auto_created(tmp_path):
    target = tmp_path / "deep" / "nested" / "wiki"
    b = LocalBackend(target)
    b.write("a.md", "x")
    assert (target / "a.md").is_file()
