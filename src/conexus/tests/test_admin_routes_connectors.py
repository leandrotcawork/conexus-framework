import json
from pathlib import Path

from fastapi.testclient import TestClient

from conexus.web.admin.app import make_admin_app


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
