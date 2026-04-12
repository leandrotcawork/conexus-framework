from pathlib import Path
from unittest.mock import MagicMock, patch

from agents.ana.tools import AnaTools
from core.memory.google_calendar import GoogleCalendarClient
from core.memory.sqlite_store import SqliteStore
from core.memory.wiki_store import WikiStore


def _make_tools(tmp_db_path: Path, tmp_wiki_dir: Path) -> AnaTools:
    store = SqliteStore(tmp_db_path)
    store.init_db()
    wiki = WikiStore(tmp_wiki_dir, autocommit=False)
    calendar = GoogleCalendarClient()
    return AnaTools(store=store, wiki=wiki, calendar=calendar)


def _mock_service():
    svc = MagicMock()
    return svc


def test_calendar_list_events(tmp_db_path, tmp_wiki_dir):
    tools = _make_tools(tmp_db_path, tmp_wiki_dir)
    mock_svc = _mock_service()
    mock_svc.events().list().execute.return_value = {
        "items": [
            {
                "id": "evt1",
                "summary": "Daily Standup",
                "start": {"dateTime": "2026-04-12T09:00:00-03:00"},
                "end": {"dateTime": "2026-04-12T09:30:00-03:00"},
                "description": "",
            }
        ]
    }
    with patch.object(tools.calendar, "_service", mock_svc):
        events = tools.calendar_list_events("2026-04-12T00:00:00Z", "2026-04-13T00:00:00Z")

    assert len(events) == 1
    assert events[0]["title"] == "Daily Standup"
    assert events[0]["id"] == "evt1"


def test_calendar_create_event(tmp_db_path, tmp_wiki_dir):
    tools = _make_tools(tmp_db_path, tmp_wiki_dir)
    mock_svc = _mock_service()
    mock_svc.events().insert().execute.return_value = {"id": "new_evt_id"}
    with patch.object(tools.calendar, "_service", mock_svc):
        result = tools.calendar_create_event(
            "Reunião com investidor",
            "2026-04-13T14:00:00-03:00",
            "2026-04-13T15:00:00-03:00",
        )

    assert result == {"id": "new_evt_id"}


def test_calendar_delete_event(tmp_db_path, tmp_wiki_dir):
    tools = _make_tools(tmp_db_path, tmp_wiki_dir)
    mock_svc = _mock_service()
    mock_svc.events().delete().execute.return_value = None
    with patch.object(tools.calendar, "_service", mock_svc):
        result = tools.calendar_delete_event("evt1")

    assert result == {"ok": True}
