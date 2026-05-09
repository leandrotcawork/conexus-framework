"""Wiki index abstraction. Reconciles a backend (file truth) with a fast index (cache)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SearchHit:
    path: str
    header_path: list[str]
    snippet: str
    score: float
    line_start: int
    line_end: int


@dataclass(frozen=True)
class PageMeta:
    path: str
    mtime_ns: int
    created: str | None
    updated: str | None
    tags: list[str]
    source: str | None
    reviewed: bool


@runtime_checkable
class WikiIndex(Protocol):
    def reindex_path(self, path: str, content: str, mtime_ns: int) -> None: ...
    def drop_path(self, path: str) -> None: ...
    def reconcile(self, paths: dict[str, int]) -> None: ...
    def search(self, query: str, k: int = 10) -> list[SearchHit]: ...
    def page_meta(self, path: str) -> PageMeta | None: ...
    def all_pages(self) -> list[PageMeta]: ...
