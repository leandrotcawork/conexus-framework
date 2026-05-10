"""WikiBackend Protocol contract + safe_join helper."""
from __future__ import annotations

import os
import pytest

from conexus.core.memory.wiki.backend import WikiBackend, safe_join


def test_protocol_runtime_checkable():
    class Stub:
        def read(self, p): return ""
        def write(self, p, c): pass
        def list(self, f=""): return []
        def search(self, q): return []
        def exists(self, p): return False
        def delete(self, p): pass

    assert isinstance(Stub(), WikiBackend)


def test_safe_join_resolves_normal_path(tmp_path):
    p = safe_join(tmp_path, "a/b.md")
    assert p == (tmp_path / "a" / "b.md").resolve()


def test_safe_join_rejects_dotdot(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, "../escape.md")


def test_safe_join_rejects_absolute(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, "/etc/passwd")


def test_safe_join_rejects_backslash(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, "a\\b.md")


def test_safe_join_rejects_empty(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, "")


@pytest.mark.skipif(os.name == "nt", reason="symlinks need admin on Windows")
def test_safe_join_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        safe_join(tmp_path, "link/x.md")
