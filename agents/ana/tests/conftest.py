from pathlib import Path

import pytest


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Pytest-tmp-path-based SQLite file. Destroyed after test."""
    return tmp_path / "conexus_test.db"


@pytest.fixture
def tmp_wiki_dir(tmp_path: Path) -> Path:
    """Empty wiki directory for tests. Destroyed after test."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    return wiki


@pytest.fixture(autouse=True)
def _env_isolation(monkeypatch):
    """Ensure tests never accidentally hit real API keys."""
    for key in [
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "TELEGRAM_BOT_TOKEN", "GOOGLE_OAUTH_REFRESH_TOKEN",
    ]:
        monkeypatch.delenv(key, raising=False)
