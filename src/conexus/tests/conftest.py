from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def studio_client(tmp_path: Path) -> TestClient:
    from conexus.web.admin.app import make_admin_app
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    ana_dir = agents_dir / "ana"
    ana_dir.mkdir()
    (ana_dir / "SKILL.md").write_text(
        "---\nname: ana\nrole: r\ngoal: g\ntools: []\nllm:\n  provider: openai\n  model: gpt-4o-mini\n---\n"
    )
    (ana_dir / "tools.py").write_text("class T:\n    def ping(self) -> str: ...\n")
    app = make_admin_app(agents_dir=agents_dir, data_dir=tmp_path / "data", repo_root=tmp_path)
    return TestClient(app)


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
