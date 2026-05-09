"""Tests for GitHubAppBackend (subprocess + LocalBackend mocked)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_FAKE_PEM = "fake-pem"
_FAKE_APP_ID = "app1"
_FAKE_INSTALL_ID = 42
_FAKE_REPO = "owner/repo"


def _subprocess_ok() -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = ""
    m.stderr = ""
    return m


def _make_backend(tmp_path: Path):
    from conexus.core.memory.wiki.github_app import GitHubAppBackend

    with patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        return GitHubAppBackend(
            local_root=tmp_path,
            repo_slug=_FAKE_REPO,
            installation_id=_FAKE_INSTALL_ID,
            app_id=_FAKE_APP_ID,
            private_key_pem=_FAKE_PEM,
        )


def test_write_then_read(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    with patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        b.write("note.md", "hello")
        content = b.read("note.md")
    assert content == "hello"


def test_list_delegates_to_local(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    with patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        b.write("a.md", "x")
        b.write("b.md", "y")
        result = b.list()
    assert sorted(result) == ["a.md", "b.md"]


def test_search_delegates_to_local(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    with patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        b.write("x.md", "the brown fox")
        hits = b.search("brown")
    assert len(hits) == 1
    assert "brown" in hits[0]["snippet"]


def test_delete(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    with patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        b.write("del.md", "bye")
        b.delete("del.md")
    assert not b.exists("del.md")


def test_exists_no_network(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    assert not b.exists("ghost.md")


def test_delete_missing_raises(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    with pytest.raises(FileNotFoundError), \
         patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        b.delete("nope.md")
