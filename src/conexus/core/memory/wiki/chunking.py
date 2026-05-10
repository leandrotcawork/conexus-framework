"""Markdown-aware splitter for wiki indexing chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .frontmatter import parse


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")


@dataclass(frozen=True)
class Chunk:
    header_path: tuple[str, ...]
    line_start: int
    line_end: int
    body: str


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _recursive_split(body: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    if _estimate_tokens(body) <= max_tokens:
        return [body]

    window_chars = max_tokens * 4
    overlap_chars = overlap_tokens * 4
    parts: list[str] = []
    start = 0

    while start < len(body):
        end = min(len(body), start + window_chars)
        parts.append(body[start:end])
        if end >= len(body):
            break
        start = max(start + 1, end - overlap_chars)

    return parts


def _body_offset_lines(text: str, body: str) -> int:
    if body == text:
        return 0
    prefix_length = len(text) - len(body)
    return text[:prefix_length].count("\n")


def markdown_chunks(text: str, max_tokens: int = 800, overlap_tokens: int = 50) -> list[Chunk]:
    _, body = parse(text)
    lines = body.splitlines()
    if not lines:
        return []

    body_offset = _body_offset_lines(text, body)
    sections: list[tuple[tuple[str, ...], int, int, str]] = []
    stack: list[tuple[int, str]] = []

    current_start = 0
    current_path: tuple[str, ...] = ()
    current_lines: list[str] = []

    def flush(end_line_idx_exclusive: int) -> None:
        if not current_lines:
            return
        start_line = current_start + 1 + body_offset
        end_line = end_line_idx_exclusive + body_offset
        sections.append((current_path, start_line, end_line, "\n".join(current_lines)))

    for idx, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            flush(idx)
            level = len(match.group(1))
            stack[:] = [(existing_level, h) for existing_level, h in stack if existing_level < level]
            stack.append((level, line.strip()))
            current_path = tuple(header for _, header in stack)
            current_start = idx
            current_lines = [line]
            continue

        if not current_lines:
            current_start = idx
            current_path = tuple(header for _, header in stack)
        current_lines.append(line)

    flush(len(lines))

    chunks: list[Chunk] = []
    for header_path, line_start, line_end, section_body in sections:
        if not section_body.strip():
            continue
        if _estimate_tokens(section_body) <= max_tokens:
            chunks.append(Chunk(header_path=header_path, line_start=line_start, line_end=line_end, body=section_body))
            continue
        for part in _recursive_split(section_body, max_tokens=max_tokens, overlap_tokens=overlap_tokens):
            if part.strip():
                chunks.append(Chunk(header_path=header_path, line_start=line_start, line_end=line_end, body=part))

    return chunks
