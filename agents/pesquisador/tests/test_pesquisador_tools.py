"""Tests for PesquisadorTools wiki operations."""

from pathlib import Path

import pytest

from agents.pesquisador.tools import PesquisadorTools
from conexus.core.memory.wiki_store import WikiStore


@pytest.fixture
def wiki(tmp_path: Path) -> WikiStore:
    wiki_dir = tmp_path / "knowledge"
    wiki_dir.mkdir()
    return WikiStore(wiki_dir, autocommit=False)


@pytest.fixture
def tools(wiki: WikiStore) -> PesquisadorTools:
    return PesquisadorTools(wiki=wiki)


def test_wiki_write_and_read(tools: PesquisadorTools):
    tools.wiki_write("domains/backend/_index.md", "# Backend\n")
    content = tools.wiki_read("domains/backend/_index.md")
    assert "# Backend" in content


def test_wiki_search(tools: PesquisadorTools):
    tools.wiki_write("domains/backend/auth/oauth2.md", "# OAuth2\nOpen Authorization 2.0")
    results = tools.wiki_search("OAuth2")
    assert len(results) >= 1
    assert "oauth2" in results[0]["path"]


def test_wiki_list(tools: PesquisadorTools):
    tools.wiki_write("domains/backend/auth/oauth2.md", "# OAuth2\n")
    tools.wiki_write("domains/backend/auth/jwt.md", "# JWT\n")
    files = tools.wiki_list("domains/backend/auth")
    assert len(files) == 2


def test_raw_save(tools: PesquisadorTools):
    result = tools.raw_save("articles", "oauth2-guide.md", "# OAuth2 Guide\nContent here.")
    assert result["ok"] is True
    content = tools.wiki_read("raw/articles/oauth2-guide.md")
    assert "OAuth2 Guide" in content


def test_raw_save_immutable(tools: PesquisadorTools):
    """raw/ files are immutable — cannot overwrite existing."""
    tools.raw_save("articles", "oauth2-guide.md", "# Original")
    result = tools.raw_save("articles", "oauth2-guide.md", "# Overwritten")
    assert result.get("error") is not None
    content = tools.wiki_read("raw/articles/oauth2-guide.md")
    assert "Original" in content


def test_web_search_classifies_trusted(tools: PesquisadorTools):
    """web_search results include is_trusted flag based on sources.md."""
    tools.wiki_write("sources.md", "## Official Documentation\n- docs.python.org\n")
    results = tools.web_search("python tutorial", max_results=3)
    # Results should have is_trusted field (True/False based on sources.md)
    for r in results:
        assert "is_trusted" in r


def test_git_sync_calls_commit(tools: PesquisadorTools, monkeypatch):
    called = []
    monkeypatch.setattr(
        tools.wiki, "_git_commit_push",
        lambda msg: called.append(msg),
    )
    tools.git_sync("test commit")
    assert len(called) == 1
    assert "test commit" in called[0]