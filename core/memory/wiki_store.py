"""WikiStore: filesystem-backed markdown wiki for agents.

Handles read/write/list/search and git autocommit. Path escape attempts
(e.g. '../') are rejected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class WikiStore:
    def __init__(self, root: str | Path, *, autocommit: bool = True):
        self.root = Path(root).resolve()
        self.autocommit = autocommit
        self.root.mkdir(parents=True, exist_ok=True)

    # ----- path safety -----

    def _resolve(self, relpath: str) -> Path:
        p = (self.root / relpath).resolve()
        try:
            p.relative_to(self.root)
        except ValueError:
            raise ValueError(f"path escapes wiki root: {relpath}")
        return p

    # ----- basic ops -----

    def read(self, relpath: str) -> str:
        p = self._resolve(relpath)
        if not p.exists():
            raise FileNotFoundError(relpath)
        return p.read_text(encoding="utf-8")

    def write(self, relpath: str, content: str) -> None:
        p = self._resolve(relpath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        if self.autocommit:
            self._git_commit_push(f"wiki: update {relpath}")

    def list(self, folder: str = "") -> list[str]:
        base = self._resolve(folder) if folder else self.root
        if not base.exists():
            return []
        out: list[str] = []
        for p in base.rglob("*.md"):
            out.append(str(p.relative_to(self.root)).replace("\\", "/"))
        return out

    def search(self, query: str) -> list[dict]:
        q = query.lower()
        hits: list[dict] = []
        for rel in self.list():
            text = self.read(rel)
            if q in text.lower():
                idx = text.lower().find(q)
                start = max(0, idx - 40)
                end = min(len(text), idx + 80)
                snippet = text[start:end].replace("\n", " ")
                hits.append({"path": rel, "snippet": snippet})
        return hits

    # ----- log & index (implemented in task 2.2) -----

    def append_log(self, kind: str, title: str, body: str) -> None:
        raise NotImplementedError  # task 2.2

    def update_index(self, path: str, summary: str) -> None:
        raise NotImplementedError  # task 2.2

    # ----- git (implemented in task 2.2) -----

    def _git_commit_push(self, message: str) -> None:
        # No-op for now; real implementation in task 2.2
        pass
