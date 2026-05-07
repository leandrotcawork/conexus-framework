import json
from conexus.core.connectors.registry import ConnectorRegistry, RegistryEntry


def test_from_file(tmp_path):
    f = tmp_path / "registry.json"
    f.write_text(json.dumps({
        "version": "1.0",
        "connectors": [{
            "name": "google_calendar",
            "version": "1.0",
            "server_url": "https://mcp.google.com/calendar",
            "scopes": ["https://www.googleapis.com/auth/calendar"],
            "ui": {
                "label": "Google Calendar",
                "icon": "calendar",
                "category": "Productivity",
                "description": "Manage calendar."
            }
        }]
    }))
    reg = ConnectorRegistry.from_file(f)
    entries = list(reg.list())
    assert len(entries) == 1
    e = entries[0]
    assert e.name == "google_calendar"
    assert e.server_url == "https://mcp.google.com/calendar"
    assert e.ui_label == "Google Calendar"
    assert reg.get("google_calendar") is e
    assert reg.get("nonexistent") is None
