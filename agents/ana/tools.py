"""Ana's tool functions. Each function is registered with CrewAI via a factory
that binds the agent's stores/clients into closures."""

from __future__ import annotations

from dataclasses import dataclass

from core.memory.google_calendar import GoogleCalendarClient
from core.memory.sqlite_store import SqliteStore
from core.memory.wiki_store import WikiStore


@dataclass
class AnaTools:
    store: SqliteStore
    wiki: WikiStore
    calendar: GoogleCalendarClient

    # ----- calendar -----

    def calendar_list_events(self, start_iso: str, end_iso: str) -> list[dict]:
        return self.calendar.list_events(start_iso, end_iso)

    def calendar_create_event(
        self, title: str, start_iso: str, end_iso: str, description: str | None = None
    ) -> dict:
        return self.calendar.create_event(title, start_iso, end_iso, description)

    def calendar_update_event(
        self,
        event_id: str,
        title: str | None = None,
        start_iso: str | None = None,
        end_iso: str | None = None,
        description: str | None = None,
    ) -> dict:
        return self.calendar.update_event(
            event_id,
            title=title,
            start_iso=start_iso,
            end_iso=end_iso,
            description=description,
        )

    def calendar_delete_event(self, event_id: str) -> dict:
        return self.calendar.delete_event(event_id)
