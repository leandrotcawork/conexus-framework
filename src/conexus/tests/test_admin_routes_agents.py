from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conexus.web.admin.app import make_admin_app


def _seed(root: Path, name: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    (d / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\nrole: test\ngoal: |\n  x\n"
        "llm:\n  provider: openai\n  model: gpt-4o-mini\n"
        "tools: []\n---\nbody"
    )
    (d / "tools.py").write_text("class T: pass\n\ndef create_cli_tools(d): return None, T()\n")


def test_list_renders_agents(tmp_path: Path) -> None:
    _seed(tmp_path, "ana")
    _seed(tmp_path, "pesq")
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert "ana" in resp.text and "pesq" in resp.text


def test_detail_shows_method_list(tmp_path: Path) -> None:
    _seed(tmp_path, "ana")
    (tmp_path / "ana" / "tools.py").write_text(
        "class T:\n"
        "    def remember(self, text: str) -> dict: return {}\n"
        "    def list_items(self, limit: int = 10) -> list: return []\n"
        "\ndef create_cli_tools(d): return None, T()\n"
    )
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/agents/ana")
    assert resp.status_code == 200
    assert "remember" in resp.text and "list_items" in resp.text


def test_detail_404_missing(tmp_path: Path) -> None:
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/agents/ghost")
    assert resp.status_code == 404


def test_get_agents_new_renders_wizard(tmp_path: Path) -> None:
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/agents/new")
    assert resp.status_code == 200
    assert "new" in resp.text.lower()
