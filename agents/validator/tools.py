"""Tools for validator agent — full framework e2e validation."""
from __future__ import annotations

from typing import ClassVar

from conexus.core.memory.sqlite_store import SqliteStore


class ValidatorTools:
    _tool_schemas: ClassVar[dict] = {
        "ping": {"description": "Health check returning {ok: true}.", "params": {}},
    }

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def ping(self) -> dict:
        return {"ok": True}


def create_cli_tools(data_dir):
    store = SqliteStore(str(data_dir) + "/conexus.db")
    store.init_db()
    return store, ValidatorTools(store)
