import json
from pathlib import Path
from conexus.core.connectors.pack import parse_connector_pack

def test_parse(tmp_path):
    pack = tmp_path / "google_calendar"
    pack.mkdir()
    (pack / "SKILL_PACK.md").write_text("""---
name: google_calendar
version: "1.0"
backend: mcp-http
data_classes: {list_events: read}
---
Body.
""", encoding="utf-8")
    (pack / "connector.json").write_text(json.dumps({
        "server_url": "https://mcp.google.com/calendar",
        "scopes": ["calendar.read"],
        "ui": {"label": "Google Calendar", "icon": "calendar",
               "category": "Productivity", "description": "Manage calendar."}
    }))
    cp = parse_connector_pack(pack / "SKILL_PACK.md")
    assert cp.skill_pack.frontmatter.name == "google_calendar"
    assert cp.connector.server_url == "https://mcp.google.com/calendar"
    assert cp.connector.scopes == ["calendar.read"]
    assert cp.connector.ui.label == "Google Calendar"


def test_google_calendar_pack():
    """Validate the shipped Google Calendar connector pack can be parsed."""
    pack_path = (
        Path(__file__).parents[5]  # project root
        / "agents/teams/_marketplace_demo/skills/google_calendar/SKILL_PACK.md"
    )
    if not pack_path.exists():
        import pytest
        pytest.skip("google_calendar pack not installed")
    cp = parse_connector_pack(pack_path)
    assert cp.skill_pack.frontmatter.name == "google_calendar"
    assert cp.connector.server_url == "https://mcp.google.com/calendar"
    assert cp.connector.scopes == ["https://www.googleapis.com/auth/calendar"]
