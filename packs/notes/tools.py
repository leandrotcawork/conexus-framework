"""Notes pack — add/list/search free-text notes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from conexus.core.memory.sqlite_store import SqliteStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NoteTools:
    _tool_schemas: ClassVar[dict] = {
        "add_note": {
            "description": (
                "Adiciona uma anotação efêmera (lista, recado curto, rascunho). "
                "NÃO use para informações pessoais permanentes (nome, família, "
                "preferências) — para isso use memory_set. NÃO use para conteúdo "
                "narrativo longo — use wiki_write."
            )
        },
        "list_notes": {
            "description": "Lista anotações efêmeras recentes (mais novas primeiro)."
        },
        "search_notes": {
            "description": "Busca por substring nas anotações efêmeras salvas."
        },
    }

    def __init__(self, store: SqliteStore, agent_name: str) -> None:
        self._store = store
        self._agent = agent_name

    def add_note(self, text: str) -> int:
        with self._store.connect() as conn:
            cur = conn.execute(
                "INSERT INTO pack_notes_entries (agent_name, text, created_at) VALUES (?, ?, ?)",
                (self._agent, text, _now_iso()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_notes(self, limit: int = 20) -> list[dict]:
        with self._store.connect() as conn:
            rows = conn.execute(
                "SELECT id, text, created_at FROM pack_notes_entries"
                " WHERE agent_name=? ORDER BY id DESC LIMIT ?",
                (self._agent, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def search_notes(self, query: str) -> list[dict]:
        like = f"%{query}%"
        with self._store.connect() as conn:
            rows = conn.execute(
                "SELECT id, text, created_at FROM pack_notes_entries"
                " WHERE agent_name=? AND text LIKE ? ORDER BY id DESC",
                (self._agent, like),
            ).fetchall()
            return [dict(r) for r in rows]


def create_tools(ctx: dict) -> NoteTools:
    return NoteTools(store=ctx["store"], agent_name=ctx["agent_name"])
