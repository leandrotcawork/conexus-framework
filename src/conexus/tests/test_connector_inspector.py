import json
from pathlib import Path
from conexus.web.admin.services.connector_inspector import list_connectors_for_agent, ConnectorEntry


def test_list_returns_only_skills_referencing_connector_packs(tmp_path: Path):
    registry = tmp_path / "packs" / "registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"version": "1.0", "entries": [{
        "id": "google_calendar", "kind": "connector", "version": "1.0",
        "source": "x", "sha": "s",
        "server_url": "https://example.com",
        "scopes": ["scope1"],
        "ui": {"label": "GCal", "icon": "calendar", "category": "Productivity",
               "description": "Read calendar."},
    }]}))
    result = list_connectors_for_agent(["google_calendar", "reminders"], registry)
    assert len(result) == 1
    assert result[0].id == "google_calendar"
    assert result[0].label == "GCal"


def test_list_empty_when_registry_missing(tmp_path: Path):
    assert list_connectors_for_agent(["x"], tmp_path / "missing.json") == []


def test_list_empty_when_no_skills_match(tmp_path: Path):
    registry = tmp_path / "packs" / "registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"version": "1.0", "entries": [
        {"id": "x", "kind": "connector", "version": "1.0", "source": "x", "sha": "s",
         "server_url": "u", "scopes": [],
         "ui": {"label": "X", "icon": "i", "category": "c", "description": "d"}}
    ]}))
    assert list_connectors_for_agent(["other"], registry) == []
