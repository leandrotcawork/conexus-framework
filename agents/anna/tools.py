"""Tools for anna."""
from __future__ import annotations

from typing import ClassVar

from conexus.core.memory.sqlite_store import SqliteStore


class AnnaTools:
    """Public methods are callable by the agent. Underscore methods are hidden."""

    _tool_schemas: ClassVar[dict] = {
        "ping": {"description": "Health check.", "params": {}},
    }

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def ping(self) -> dict:
        """Health check."""
        return {"ok": True}


def create_cli_tools(data_dir):
    store = SqliteStore(str(data_dir) + "/conexus.db")
    return store, AnnaTools(store)
