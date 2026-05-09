"""Built-in identity tools — auto-registered when identity.enabled in SKILL.md.

Tools exposed (each becomes available to the agent via tool calling):
  - memory_get(key) -> {"key", "value"} | None
  - memory_set(key, value) -> {"ok": True}
  - memory_list_facts() -> list[{"key", "value", "updated_at"}]
  - memory_delete(key) -> {"deleted": bool}
  - block_get(name) -> str | None
  - block_set(name, content) -> {"ok": True}
  - block_list() -> list[{"name", "content", "budget_chars"}]
  - wiki_read(path) -> str
  - wiki_list(folder?) -> list[str]
  - wiki_search(query) -> list[{"path", "snippet"}]
  - wiki_write(path, content) -> {"ok": True}
  - wiki_append_log(kind, title, body) -> {"ok": True}
"""
from __future__ import annotations

from conexus.core.identity.blocks import BlockStore, BlockOverBudgetError
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


class IdentityTools:
    def __init__(
        self,
        agent_id: str,
        store: SqliteStore,
        wiki: WikiStore | None,
        blocks: BlockStore,
        block_specs: dict[str, int],
    ):
        self._agent_id = agent_id
        self._store = store
        self._wiki = wiki
        self._blocks = blocks
        self._block_specs = block_specs  # name -> budget_chars

    # ---- facts ----

    def memory_get(self, key: str) -> dict | None:
        v = self._store.fact_get(self._agent_id, key)
        if v is None:
            return None
        return {"key": key, "value": v}

    def memory_set(self, key: str, value: str) -> dict:
        self._store.fact_set(self._agent_id, key, value)
        return {"ok": True, "key": key}

    def memory_list_facts(self) -> list[dict]:
        return self._store.facts_list(self._agent_id)

    def memory_delete(self, key: str) -> dict:
        return {"deleted": self._store.fact_delete(self._agent_id, key)}

    # ---- blocks ----

    def block_get(self, name: str) -> str | None:
        return self._blocks.get(self._agent_id, name)

    def block_set(self, name: str, content: str) -> dict:
        if name not in self._block_specs:
            raise ValueError(f"block {name!r} not declared in identity.blocks")
        budget = self._block_specs[name]
        try:
            self._blocks.set(self._agent_id, name, content, budget)
        except BlockOverBudgetError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "name": name}

    def block_list(self) -> list[dict]:
        return self._blocks.list(self._agent_id)

    # ---- wiki ----

    def _require_wiki(self) -> WikiStore:
        if self._wiki is None:
            raise RuntimeError("wiki not configured: set identity.wiki.dir in SKILL.md")
        return self._wiki

    def wiki_read(self, path: str) -> str:
        return self._require_wiki().read(path)

    def wiki_list(self, folder: str = "") -> list[str]:
        return self._require_wiki().list(folder)

    def wiki_search(self, query: str) -> list[dict]:
        return self._require_wiki().search(query)

    def wiki_write(self, path: str, content: str) -> dict:
        self._require_wiki().write(path, content)
        return {"ok": True, "path": path}

    def wiki_append_log(self, kind: str, title: str, body: str = "") -> dict:
        self._require_wiki().append_log(kind, title, body)
        return {"ok": True}

    def wiki_delete(self, path: str) -> dict:
        self._require_wiki().delete(path)
        return {"deleted": path}

    def wiki_exists(self, path: str) -> bool:
        return self._require_wiki().exists(path)

    def wiki_move(self, src: str, dst: str) -> dict:
        self._require_wiki().move(src, dst)
        return {"moved": src, "to": dst}

    def wiki_lint(self) -> dict:
        report = self._require_wiki().lint()
        dead_links = [list(link) for link in report.dead_links]
        return {"dead_links": dead_links, "warnings": report.warnings}

    def wiki_index_update(self, path: str, summary: str) -> dict:
        self._require_wiki().index_update(path, summary)
        return {"indexed": path}
