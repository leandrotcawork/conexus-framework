"""Ana's tool functions. Each function is registered with CrewAI via a factory
that binds the agent's stores/clients into closures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore

if TYPE_CHECKING:
    from conexus.core.memory.google_calendar import GoogleCalendarClient
else:
    GoogleCalendarClient = Any


@dataclass
class AnaTools:
    store: SqliteStore
    wiki: WikiStore
    calendar: GoogleCalendarClient
    _tool_schemas: ClassVar[dict] = None  # set below to avoid dataclass field issues

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


AnaTools._tool_schemas = {
    "calendar_list_events": {
        "description": "Lista eventos do Google Calendar num intervalo de datas.",
        "params": {
            "start_iso": {"description": "Início ISO 8601, ex: 2026-04-12T00:00:00-03:00"},
            "end_iso": {"description": "Fim ISO 8601"},
        }
    },
    "calendar_create_event": {
        "description": "Cria um evento no Google Calendar. Verifica conflitos automaticamente. Se houver conflito, retorna os eventos existentes e pede confirmacao ao Leandro. Use force=true SOMENTE quando o Leandro confirmar que quer manter os dois.",
        "params": {
            "start_iso": {"description": "Início ISO 8601"},
            "end_iso": {"description": "Fim ISO 8601"},
            "force": {"description": "Se true, cria mesmo com conflito. Use SOMENTE apos confirmacao do Leandro."},
        }
    },
    "calendar_update_event": {"description": "Atualiza um evento existente no Google Calendar."},
    "calendar_delete_event": {"description": "Remove um evento do Google Calendar."},
    "memory_get": {"description": "Busca um fato específico da memória pelo nome da chave."},
    "memory_set": {"description": "Salva um fato na memória persistente."},
    "memory_list_facts": {"description": "Lista todos os fatos salvos na memória."},
    "todos_add": {
        "description": "Adiciona uma tarefa/todo.",
        "params": {"due_iso": {"description": "Vencimento ISO 8601 (opcional)"}}
    },
    "todos_list": {
        "description": "Lista tarefas/todos.",
        "params": {"status": {"enum": ["open", "done", "all"]}}
    },
    "todos_mark_done": {"description": "Marca uma tarefa como concluída pelo ID."},
    "wiki_read": {
        "description": "Lê um arquivo da wiki. O path é relativo à raiz da wiki, ex: 'index.md'. NUNCA inclua 'agents/ana/wiki/' no path.",
        "params": {"path": {"description": "Caminho relativo, ex: 'preferences/leandro.md'"}}
    },
    "wiki_list": {"description": "Lista arquivos da wiki. Use folder='' para listar a raiz. NUNCA inclua 'agents/ana/wiki/' no folder."},
    "wiki_search": {"description": "Busca conteúdo na wiki."},
    "wiki_write": {
        "description": "Escreve ou atualiza um arquivo na wiki. O path é relativo à raiz da wiki. NUNCA inclua 'agents/ana/wiki/' no path.",
        "params": {"path": {"description": "Caminho relativo, ex: 'preferences/leandro.md'"}}
    },
    "wiki_append_log": {"description": "Faz append em log.md da wiki."},
    "wiki_update_index": {"description": "Atualiza index.md da wiki."},
}
