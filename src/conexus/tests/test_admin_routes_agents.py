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
    """Regression: /admin/agents/new must NOT be shadowed by /admin/agents/{name}."""
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/agents/new")
    assert resp.status_code == 200
    assert "New agent" in resp.text


def test_save_writes_skill_md(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "ana", template="chat-only")
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post("/admin/agents/ana", data={
        "role": "updated role", "goal": "new goal",
        "llm_provider": "openai", "llm_model": "gpt-4o-mini", "llm_temperature": "0.5",
        "tools": "ping", "body": "new body",
    })
    assert resp.status_code == 200
    text = (tmp_path / "ana" / "SKILL.md").read_text(encoding="utf-8")
    assert "updated role" in text
    assert "new body" in text


def test_save_blocks_invalid(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "ana", template="chat-only")
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post("/admin/agents/ana", data={
        "role": "x", "goal": "x", "llm_provider": "openai",
        "llm_model": "gpt-4o-mini", "llm_temperature": "0.5",
        "tools": "ghost_method", "body": "x",
    })
    assert resp.status_code == 422
    assert "ghost_method" in resp.text


def test_new_agent_creates_folder(tmp_path: Path) -> None:
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post(
        "/admin/agents/new", data={"name": "newbie", "template": "chat-only"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/agents/newbie"
    assert (tmp_path / "newbie" / "SKILL.md").exists()


def test_new_agent_rejects_bad_name(tmp_path: Path) -> None:
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post("/admin/agents/new", data={"name": "Bad-Name", "template": "chat-only"})
    assert resp.status_code == 400


def test_delete_removes_folder(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "doomed", template="chat-only")
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.delete("/admin/agents/doomed")
    assert resp.status_code == 204
    assert not (tmp_path / "doomed").exists()


def test_delete_404_when_missing(tmp_path: Path) -> None:
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    assert client.delete("/admin/agents/ghost").status_code == 404


def test_preview_returns_yaml(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "ana", template="chat-only")
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post("/admin/agents/ana/preview", data={
        "role": "preview only", "goal": "g",
        "llm_provider": "openai", "llm_model": "gpt-4o-mini", "llm_temperature": "0.4",
        "tools": "ping", "body": "x",
    })
    assert resp.status_code == 200
    assert "preview only" in resp.text
    assert "preview only" not in (tmp_path / "ana" / "SKILL.md").read_text()
