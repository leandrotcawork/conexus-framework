"""Read-only wiki health checks."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .frontmatter import parse


_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_INDEX_EXCLUDED = {"index.md", "log.md"}
_STUB_THRESHOLD = 200


@dataclass(frozen=True)
class LintReport:
    orphans: list[str]
    dead_links: list[tuple[str, str]]
    missing_frontmatter: list[str]
    stub_pages: list[str]
    stale_index: list[str]

    @property
    def total_issues(self) -> int:
        return (
            len(self.orphans)
            + len(self.dead_links)
            + len(self.missing_frontmatter)
            + len(self.stub_pages)
            + len(self.stale_index)
        )


def _normalize_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target or target.startswith(("http://", "https://", "mailto:", "#")):
        return None

    no_query = target.split("?", 1)[0]
    no_fragment = no_query.split("#", 1)[0]
    if not no_fragment.endswith(".md"):
        return None

    return no_fragment


def _extract_targets(markdown: str) -> set[str]:
    targets: set[str] = set()
    for match in _MARKDOWN_LINK_RE.finditer(markdown):
        normalized = _normalize_target(match.group(1))
        if normalized:
            targets.add(normalized)
    return targets


def lint_wiki(store) -> LintReport:
    backend = store.backend if hasattr(store, "backend") else store._backend
    pages = sorted(path for path in backend.list() if path.endswith(".md"))
    page_set = set(pages)

    index_targets: set[str] = set()
    if "index.md" in page_set:
        index_targets = _extract_targets(backend.read("index.md"))

    orphans: list[str] = []
    dead_links: list[str] = []
    missing_frontmatter: list[str] = []
    stub_pages: list[str] = []

    for path in pages:
        text = backend.read(path)
        try:
            meta, body = parse(text)
        except ValueError:
            meta, body = {}, text

        if path not in _INDEX_EXCLUDED and not meta:
            missing_frontmatter.append(path)

        if path not in _INDEX_EXCLUDED and len(body.strip()) < _STUB_THRESHOLD:
            stub_pages.append(path)

        if path not in _INDEX_EXCLUDED and path not in index_targets:
            orphans.append(path)

        for target in sorted(_extract_targets(body)):
            if target not in page_set:
                dead_links.append((path, target))

    stale_index = sorted(target for target in index_targets if target not in page_set)

    return LintReport(
        orphans=orphans,
        dead_links=dead_links,
        missing_frontmatter=missing_frontmatter,
        stub_pages=stub_pages,
        stale_index=stale_index,
    )
