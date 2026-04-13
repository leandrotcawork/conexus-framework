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
        self, title: str, start_iso: str, end_iso: str, description: str | None = None,
        force: bool = False,
    ) -> dict:
        # Check for overlapping events unless force=True
        if not force:
            existing = self.calendar.list_events(start_iso, end_iso)
            if existing:
                conflicts = [f"- {e.get('summary', '(sem titulo)')} ({e.get('start', '')} ~ {e.get('end', '')})" for e in existing]
                return {
                    "conflict": True,
                    "message": f"Conflito de horario! Ja existem {len(existing)} evento(s) nesse periodo:\n" + "\n".join(conflicts),
                    "hint": "Pergunte ao Leandro como ele quer proceder: reagendar, manter os dois, ou cancelar.",
                }
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

    # ----- memory -----

    def memory_get(self, key: str) -> str | None:
        return self.store.fact_get(key)

    def memory_set(self, key: str, value: str) -> dict:
        self.store.fact_set(key, value)
        return {"ok": True}

    def memory_list_facts(self) -> list[dict]:
        return self.store.facts_list()

    # ----- todos -----

    def todos_add(self, text: str, due_iso: str | None = None) -> dict:
        return {"id": self.store.todo_add(text, due_iso)}

    def todos_list(self, status: str = "open") -> list[dict]:
        return self.store.todos_list(status)

    def todos_mark_done(self, id: int) -> dict:
        self.store.todo_mark_done(id)
        return {"ok": True}

    # ----- wiki -----

    def wiki_read(self, path: str) -> str:
        return self.wiki.read(path)

    def wiki_list(self, folder: str = "") -> list[str]:
        return self.wiki.list(folder)

    def wiki_search(self, query: str) -> list[dict]:
        return self.wiki.search(query)

    def wiki_write(self, path: str, content: str) -> dict:
        self.wiki.write(path, content)
        return {"ok": True}

    def wiki_append_log(self, kind: str, title: str, body: str) -> dict:
        self.wiki.append_log(kind, title, body)
        return {"ok": True}

    def wiki_update_index(self, path: str, summary: str) -> dict:
        self.wiki.update_index(path, summary)
        return {"ok": True}
