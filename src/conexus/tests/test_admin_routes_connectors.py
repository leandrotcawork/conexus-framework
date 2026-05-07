import json
from pathlib import Path

from fastapi.testclient import TestClient

from conexus.web.admin.app import make_admin_app


def _scaffold(tmp_path: Path, name: str) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, name, template="chat-only")


def test_marketplace_renders_registry(tmp_path: Path) -> None:
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps({"version": "1.0", "connectors": [{
        "name": "google_calendar", "version": "1.0",
        "server_url": "https://mcp.google.com/calendar",
        "scopes": ["calendar.readonly"],
        "ui": {"label": "Google Calendar", "icon": "🗓", "category": "Productivity",
               "description": "Read + create events."}
    }]}))
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path, connectors_registry_path=reg)
    client = TestClient(app)
    resp = client.get("/admin/connectors")
    assert resp.status_code == 200
    assert "Google Calendar" in resp.text
    assert "🗓" in resp.text


def test_diff_endpoint_returns_summary(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "ana", template="chat-only")
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps({"version": "1.0", "connectors": [{
        "name": "notion", "version": "1.0", "server_url": "https://mcp.notion.so",
        "scopes": ["read"],
        "ui": {"label": "Notion", "icon": "📓", "category": "Docs", "description": "x"}}]}))
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path, connectors_registry_path=reg)
    client = TestClient(app)
    resp = client.get("/admin/connectors/notion/diff", params={"agent": "ana"})
    assert resp.status_code == 200
    assert "tools" in resp.text.lower()


def test_install_route_writes_pack(tmp_path: Path) -> None:
    _scaffold(tmp_path, "ana")
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps({"version": "1.0", "connectors": [{
        "name": "notion", "version": "1.0", "server_url": "https://mcp.notion.so",
        "scopes": ["read"],
        "ui": {"label": "Notion", "icon": "📓", "category": "Docs", "description": "x"}}]}))
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path, connectors_registry_path=reg)
    client = TestClient(app)
    resp = client.post(
        "/admin/connectors/notion/install", data={"agent": "ana"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/agents/ana"
    assert (tmp_path / "ana" / "skills" / "notion" / "connector.json").exists()
