"""WikiStore: facade over a backend, optionally enriched by a WikiIndex.
Index path enables FTS search, frontmatter discipline, citation metadata.
Without an index the store falls back to legacy substring search."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from conexus.core.memory.wiki import LocalBackend, WikiBackend
from conexus.core.memory.wiki.frontmatter import inject, parse, today_iso, validate
from conexus.core.memory.wiki.index import WikiIndex


class WikiStore:
    def __init__(
        self,
        backend_or_root: WikiBackend | str | Path,
        index: WikiIndex | None = None,
    ) -> None:
        if isinstance(backend_or_root, (str, Path)):
            self._backend: WikiBackend = LocalBackend(backend_or_root)
        else:
            self._backend = backend_or_root
        self._index = index

    @classmethod
    def local(cls, root: str | Path) -> "WikiStore":
        return cls(LocalBackend(root))

    # ----- read / list -----

    def read(self, path: str) -> str:
        return self._backend.read(path)

    def list(self, folder: str = "") -> list[str]:
        return self._backend.list(folder)

    def exists(self, path: str) -> bool:
        return self._backend.exists(path)

    # ----- write / delete / move -----

    def write(self, path: str, content: str) -> dict:
        defaults = {
            "created": today_iso(),
            "updated": today_iso(),
            "tags": [],
            "source": None,
            "reviewed": False,
        }
        try:
            content = inject(content, defaults)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        meta, _ = parse(content)
        warnings = validate(meta)
        self._backend.write(path, content)
        if self._index:
            self._index.reindex_path(path, content, self._mtime_ns(path))
        return {"ok": True, "path": path, "warnings": warnings}

    def delete(self, path: str) -> dict:
        self._backend.delete(path)
        if self._index:
            self._index.drop_path(path)
        return {"ok": True, "path": path}

    def move(self, src: str, dst: str) -> dict:
        content = self._backend.read(src)
        self._backend.write(dst, content)
        self._backend.delete(src)
        backlinks_updated = self._update_backlinks(src, dst)
        if self._index:
            self._index.drop_path(src)
            self._index.reindex_path(dst, content, self._mtime_ns(dst))
        return {
            "ok": True,
            "src": src,
            "dst": dst,
            "backlinks_updated": backlinks_updated,
        }

    # ----- search -----

    def search(self, query: str, k: int = 10) -> list[dict]:
        if self._index is None:
            return self._backend.search(query)
        self._reconcile()
        hits = self._index.search(query, k=k)
        return [
            {
                "path": h.path,
                "header_path": h.header_path,
                "snippet": h.snippet,
                "score": h.score,
                "line_start": h.line_start,
                "line_end": h.line_end,
            }
            for h in hits
        ]

    # ----- conveniences -----

    def append_log(self, kind: str, title: str, body: str = "") -> None:
        ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## [{ts}] {kind} | {title}\n{body}\n"
        existing = self._backend.read("log.md") if self._backend.exists("log.md") else "# Wiki Log\n\n"
        self.write("log.md", existing + entry)

    def update_index(self, path: str, summary: str) -> None:
        existing = self._backend.read("index.md") if self._backend.exists("index.md") else "# Wiki Index\n\n"
        meta, body = parse(existing)
        lines = [ln for ln in body.splitlines() if f"({path})" not in ln]
        label = Path(path).stem
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lines.append(f"- [{label}]({path}) - {summary} ({date_str})")
        new_body = "\n".join(lines) + "\n"
        if meta:
            self.write("index.md", new_body)
        else:
            self.write("index.md", new_body)

    @property
    def backend(self) -> WikiBackend:
        return self._backend

    @property
    def index(self) -> WikiIndex | None:
        return self._index

    # ----- internals -----

    def _mtime_ns(self, path: str) -> int:
        try:
            root = getattr(self._backend, "root", None)
            if root is None:
                return 0
            return (Path(root) / path).stat().st_mtime_ns
        except Exception:
            return 0

    def _reconcile(self) -> None:
        if self._index is None:
            return
        root = getattr(self._backend, "root", None)
        if root is None:
            return
        paths: dict[str, int] = {}
        for rel in self._backend.list():
            try:
                paths[rel] = (Path(root) / rel).stat().st_mtime_ns
            except OSError:
                continue
        self._index.reconcile(paths)

    def _update_backlinks(self, src: str, dst: str) -> int:
        pat = re.compile(r"\[([^\]]*)\]\(" + re.escape(src) + r"((?:#[^)]+)?)\)")
        wikilink = re.compile(r"\[\[" + re.escape(src) + r"((?:#[^\]]+)?)\]\]")
        citation = re.compile(r"\[" + re.escape(src) + r"((?:#[\w-]+))?\](?!\()")
        count = 0
        for rel in self._backend.list():
            text = self._backend.read(rel)
            new = pat.sub(rf"[\1]({dst}\2)", text)
            new = wikilink.sub(rf"[[{dst}\1]]", new)
            new = citation.sub(rf"[{dst}\1]", new)
            if new != text:
                self._backend.write(rel, new)
                if self._index:
                    self._index.reindex_path(rel, new, self._mtime_ns(rel))
                count += 1
        return count
