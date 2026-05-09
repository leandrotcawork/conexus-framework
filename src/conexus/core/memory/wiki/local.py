"""Filesystem wiki backend. Default for new agents. No auth, no network, no git."""
from __future__ import annotations

from pathlib import Path

from conexus.core.memory.wiki.backend import safe_join


class LocalBackend:
    """Plain directory wiki. Markdown files under `root`. POSIX-relative paths."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, path: str) -> str:
        p = safe_join(self.root, path)
        if not p.exists():
            raise FileNotFoundError(path)
        return p.read_text(encoding="utf-8")

    def write(self, path: str, content: str) -> None:
        p = safe_join(self.root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def list(self, folder: str = "") -> list[str]:
        folder = folder.strip("/\\") if folder else ""
        base = safe_join(self.root, folder) if folder else self.root
        if not base.exists():
            return []
        return sorted(
            str(p.relative_to(self.root)).replace("\\", "/")
            for p in base.rglob("*.md")
        )

    def search(self, query: str) -> list[dict]:
        q = query.lower()
        hits: list[dict] = []
        for rel in self.list():
            text = self.read(rel)
            idx = text.lower().find(q)
            if idx < 0:
                continue
            start = max(0, idx - 40)
            end = min(len(text), idx + 80)
            hits.append({"path": rel, "snippet": text[start:end].replace("\n", " ")})
        return hits

    def exists(self, path: str) -> bool:
        try:
            return safe_join(self.root, path).exists()
        except ValueError:
            return False

    def delete(self, path: str) -> None:
        p = safe_join(self.root, path)
        if not p.exists():
            raise FileNotFoundError(path)
        p.unlink()
