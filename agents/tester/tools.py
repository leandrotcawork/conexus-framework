"""Tools for tester agent — Phase A-D end-to-end validation."""
from __future__ import annotations

from typing import ClassVar

from conexus.core.memory.sqlite_store import SqliteStore


class TesterTools:
    """Native tools surface for tester agent."""

    _tool_schemas: ClassVar[dict] = {
        "ping": {"description": "Health check returning {ok: true}.", "params": {}},
    }

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def ping(self) -> dict:
        """Health check."""
        return {"ok": True}


def create_cli_tools(data_dir):
    store = SqliteStore(str(data_dir) + "/conexus.db")
    store.init_db()
    return store, TesterTools(store)
