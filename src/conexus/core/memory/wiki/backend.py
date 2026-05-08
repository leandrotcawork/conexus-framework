"""Wiki storage backend protocol. Implementations: LocalBackend, GitHubAppBackend (Phase 2)."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class WikiBackend(Protocol):
    """Filesystem-shaped contract for wiki storage. Paths are POSIX-style relative."""

    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str) -> None: ...
    def list(self, folder: str = "") -> list[str]: ...
    def search(self, query: str) -> list[dict]: ...
    def exists(self, path: str) -> bool: ...
    def delete(self, path: str) -> None: ...


def safe_join(root: Path, relpath: str) -> Path:
    """Resolve `relpath` under `root`. Reject escapes, absolute paths, symlinks-out."""
    if not relpath or relpath.startswith("/") or "\\" in relpath:
        raise ValueError(f"invalid wiki path: {relpath!r}")
    p = (root / relpath).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError as e:
        raise ValueError(f"path escapes wiki root: {relpath!r}") from e
    return p
