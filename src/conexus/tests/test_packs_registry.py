import json
from pathlib import Path
import pytest
from conexus.core.packs.registry import PacksRegistry, PackEntry, RegistryError


def _make_registry(tmp: Path, entries: list[dict]) -> Path:
    p = tmp / "packs" / "registry.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": "1.0", "entries": entries}))
    return p


def test_load_skill_entry(tmp_path: Path):
    p = _make_registry(tmp_path, [{
        "id": "reminders", "kind": "skill", "version": "0.1.0",
        "source": "packs/reminders", "sha": "abc123",
        "ui": {"label": "Reminders", "icon": "bell", "category": "Productivity",
               "description": "Schedule reminders."}
    }])
    reg = PacksRegistry.load(p)
    e = reg.get("reminders")
    assert e.kind == "skill"
    assert e.version == "0.1.0"
    assert e.sha == "abc123"


def test_load_connector_entry(tmp_path: Path):
    p = _make_registry(tmp_path, [{
        "id": "google_calendar", "kind": "connector", "version": "1.0",
        "source": "https://github.com/conexus/connectors/google_calendar",
        "sha": "def456",
        "server_url": "https://mcp.google.com/calendar",
        "scopes": ["https://www.googleapis.com/auth/calendar"],
        "ui": {"label": "Google Calendar", "icon": "calendar",
               "category": "Productivity", "description": "Read calendar."}
    }])
    reg = PacksRegistry.load(p)
    e = reg.get("google_calendar")
    assert e.kind == "connector"
    assert e.server_url == "https://mcp.google.com/calendar"
    assert e.scopes == ["https://www.googleapis.com/auth/calendar"]


def test_get_unknown_raises(tmp_path: Path):
    p = _make_registry(tmp_path, [])
    reg = PacksRegistry.load(p)
    with pytest.raises(RegistryError):
        reg.get("nope")


def test_filter_by_kind(tmp_path: Path):
    p = _make_registry(tmp_path, [
        {"id": "a", "kind": "skill", "version": "1", "source": "x", "sha": "s",
         "ui": {"label": "A", "icon": "i", "category": "c", "description": "d"}},
        {"id": "b", "kind": "connector", "version": "1", "source": "x", "sha": "s",
         "server_url": "u", "scopes": [],
         "ui": {"label": "B", "icon": "i", "category": "c", "description": "d"}},
    ])
    reg = PacksRegistry.load(p)
    assert [e.id for e in reg.list(kind="skill")] == ["a"]
    assert [e.id for e in reg.list(kind="connector")] == ["b"]
    assert {e.id for e in reg.list()} == {"a", "b"}
