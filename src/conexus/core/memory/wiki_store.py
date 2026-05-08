"""WikiStore: thin facade over a WikiBackend.

Phase 1 ships LocalBackend only. Phase 2 adds GitHubAppBackend with remote sync.
Append-log and index helpers are framework-level conveniences that delegate to
the backend.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from conexus.core.memory.wiki import LocalBackend, WikiBackend


class WikiStore:
    def __init__(self, backend_or_root: WikiBackend | str | Path) -> None:
        if isinstance(backend_or_root, (str, Path)):
            # Back-compat shim: legacy callers pass a path; build LocalBackend.
            self._backend: WikiBackend = LocalBackend(backend_or_root)
        else:
            self._backend = backend_or_root

    @classmethod
    def local(cls, root: str | Path) -> "WikiStore":
        return cls(LocalBackend(root))

    # ----- delegation -----

    def read(self, path: str) -> str:
        return self._backend.read(path)

    def write(self, path: str, content: str) -> None:
        self._backend.write(path, content)

    def list(self, folder: str = "") -> list[str]:
        return self._backend.list(folder)

    def search(self, query: str) -> list[dict]:
        return self._backend.search(query)

    def delete(self, path: str) -> None:
        self._backend.delete(path)

    # ----- conveniences -----

    def append_log(self, kind: str, title: str, body: str = "") -> None:
        ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## [{ts}] {kind} | {title}\n{body}\n"
        existing = self._backend.read("log.md") if self._backend.exists("log.md") else "# Wiki Log\n\n"
        self._backend.write("log.md", existing + entry)

    def update_index(self, path: str, summary: str) -> None:
        existing = self._backend.read("index.md") if self._backend.exists("index.md") else "# Wiki Index\n\n"
        lines = [ln for ln in existing.splitlines() if f"({path})" not in ln]
        label = Path(path).stem
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lines.append(f"- [{label}]({path}) — {summary} ({date_str})")
        self._backend.write("index.md", "\n".join(lines) + "\n")
