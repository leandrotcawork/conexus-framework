from pathlib import Path
import json

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
        "---\nname: ana\nrole: r\ngoal: g\ntools: []\nllm:\n  provider: openai\n  model: gpt-4o-mini\nskills: []\n---\n"
    )
    (ana_dir / "tools.py").write_text("class T:\n    def ping(self) -> str: ...\n")
    # seed a demo pack + registry for D2/D3 tests
    demo_pack = tmp_path / "packs" / "demo"
    demo_pack.mkdir(parents=True)
    (demo_pack / "SKILL_PACK.md").write_text(
        "---\nname: demo\nversion: 0.1.0\nbackend: python\n---\nbody"
    )
    (demo_pack / "tools.py").write_text("class Tools:\n    def hi(self) -> str: ...\n")
    (tmp_path / "packs" / "registry.json").write_text(json.dumps({"version": "1.0", "entries": [
        {"id": "demo", "kind": "skill", "version": "0.1.0",
         "source": "packs/demo", "sha": "abc",
         "ui": {"label": "Demo", "icon": "puzzle", "category": "Skills", "description": "Demo pack."}}
    ]}))
    app = make_admin_app(agents_dir=agents_dir, data_dir=tmp_path / "data", repo_root=tmp_path)
    return TestClient(app)


@pytest.fixture
def tmp_db_path() -> str:
    """In-memory SQLite — fast, isolated per test."""
    return ":memory:"


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
