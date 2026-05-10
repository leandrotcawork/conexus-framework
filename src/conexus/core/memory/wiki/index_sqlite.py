"""SQLite FTS5 implementation of WikiIndex. Mtime-reconciled cache over WikiBackend."""
from __future__ import annotations

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.backend import WikiBackend
from conexus.core.memory.wiki.chunking import markdown_chunks
from conexus.core.memory.wiki.frontmatter import parse as parse_frontmatter
from conexus.core.memory.wiki.index import PageMeta, SearchHit, WikiIndex


class SqliteFtsIndex(WikiIndex):
    def __init__(self, *, store: SqliteStore, agent_id: str, backend: WikiBackend) -> None:
        self._store = store
        self._agent_id = agent_id
        self._backend = backend

    def reindex_path(self, path: str, content: str, mtime_ns: int) -> None:
        meta, _ = parse_frontmatter(content)
        self._store.wiki_page_set(
            self._agent_id,
            path,
            mtime_ns=mtime_ns,
            created=meta.get("created"),
            updated=meta.get("updated"),
            tags=meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
            source=meta.get("source"),
            reviewed=bool(meta.get("reviewed", False)),
        )
        self._store.wiki_chunks_clear(self._agent_id, path)
        for ch in markdown_chunks(content):
            self._store.wiki_chunk_insert(
                self._agent_id,
                path,
                header_path=list(ch.header_path),
                line_start=ch.line_start,
                line_end=ch.line_end,
                body=ch.body,
            )

    def drop_path(self, path: str) -> None:
        self._store.wiki_page_delete(self._agent_id, path)

    def reconcile(self, paths: dict[str, int]) -> None:
        stored = {p["path"]: p["mtime_ns"] for p in self._store.wiki_page_list(self._agent_id)}
        for path, mt in paths.items():
            if stored.get(path, -1) < mt:
                content = self._backend.read(path)
                self._reindex_from_backend(path, content)
        for path in stored.keys() - paths.keys():
            self.drop_path(path)

    def _reindex_from_backend(self, path: str, content: str) -> None:
        try:
            from pathlib import Path as _P

            p = _P(getattr(self._backend, "root", _P("."))) / path
            mtime_ns = p.stat().st_mtime_ns
        except Exception:
            mtime_ns = 0
        self.reindex_path(path, content, mtime_ns)

    def search(self, query: str, k: int = 10) -> list[SearchHit]:
        rows = self._store.wiki_fts_search(self._agent_id, query, k=k)
        return [
            SearchHit(
                path=r["path"],
                header_path=r["header_path"],
                snippet=r["snippet"],
                score=r["score"],
                line_start=r["line_start"],
                line_end=r["line_end"],
            )
            for r in rows
        ]

    def page_meta(self, path: str) -> PageMeta | None:
        row = self._store.wiki_page_get(self._agent_id, path)
        if row is None:
            return None
        return PageMeta(
            path=row["path"],
            mtime_ns=row["mtime_ns"],
            created=row["created"],
            updated=row["updated"],
            tags=row["tags"],
            source=row["source"],
            reviewed=row["reviewed"],
        )

    def all_pages(self) -> list[PageMeta]:
        return [
            PageMeta(
                path=r["path"],
                mtime_ns=r["mtime_ns"],
                created=r["created"],
                updated=r["updated"],
                tags=r["tags"],
                source=r["source"],
                reviewed=r["reviewed"],
            )
            for r in self._store.wiki_page_list(self._agent_id)
        ]
