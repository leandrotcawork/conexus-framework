"""One-shot migration: inject frontmatter where missing + build initial FTS index."""
from __future__ import annotations

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.backend import WikiBackend
from conexus.core.memory.wiki.frontmatter import inject, parse, today_iso
from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex


def migrate_agent_wiki(agent_id: str, backend: WikiBackend, store: SqliteStore) -> dict:
    idx = SqliteFtsIndex(store=store, agent_id=agent_id, backend=backend)
    pages = backend.list()
    injected = 0
    for path in pages:
        content = backend.read(path)
        meta, _ = parse(content)
        if not meta:
            content = inject(content, {"created": today_iso(), "updated": today_iso(),
                                       "tags": [], "source": "migrate", "reviewed": False})
            backend.write(path, content)
            injected += 1
        try:
            from pathlib import Path as _P
            mt = (_P(getattr(backend, "root", _P("."))) / path).stat().st_mtime_ns
        except Exception:
            mt = 0
        idx.reindex_path(path, content, mt)
    return {"pages_processed": len(pages), "frontmatter_injected": injected}
