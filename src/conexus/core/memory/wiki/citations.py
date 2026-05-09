"""Citation format: [path#header_anchor]. Helpers to format, parse, slugify."""
from __future__ import annotations

import re

_SLUG_NORMALIZE = re.compile(r"[^\w\s-]+", re.UNICODE)
_SLUG_SPACES = re.compile(r"[\s-]+")
_CITATION_RE = re.compile(r"\[([^\[\]\s()]+\.md)(?:#([a-z0-9-]+))?\]")


def slug_anchor(heading: str) -> str:
    """Convert a markdown heading to a URL-style slug anchor."""
    text = heading.lstrip("#").strip().lower()
    text = _SLUG_NORMALIZE.sub("", text)
    text = _SLUG_SPACES.sub("-", text)
    return text.strip("-")


def format_citation(path: str, header_path: list[str]) -> str:
    """Format a citation reference in wiki citation syntax."""
    if not header_path:
        return f"[{path}]"
    return f"[{path}#{slug_anchor(header_path[-1])}]"


def parse_citations(text: str) -> list[tuple[str, str]]:
    """Return list of (path, anchor) tuples; anchor is empty when absent."""
    return [(m.group(1), m.group(2) or "") for m in _CITATION_RE.finditer(text)]
