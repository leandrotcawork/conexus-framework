# Wiki Tools Redesign Implementation Plan

> **For Claude controller:** Dispatch every task via `/codex:rescue --model gpt-5.3-codex --wait`. Group tasks by **Wave** — tasks within a wave run in **parallel** (one Agent message with multiple tool calls). Waves run **sequentially** — finish wave N before dispatching wave N+1. After each task: `/simplify` pass, run targeted tests, commit. After each wave: spec-compliance + code-quality review.

**Goal:** Ship the wiki redesign from `docs/superpowers/specs/2026-05-09-wiki-tools-redesign-design.md` — FTS5 BM25 over markdown chunks, frontmatter discipline, expanded tool surface, lint, citations.

**Architecture:** `WikiStore` composes existing `WikiBackend` with new `WikiIndex` (`SqliteFtsIndex`). Two sources of truth (`.md` files + SQLite cache) reconciled by mtime. Pure modules (chunking/frontmatter/citations) have zero deps; everything else composes them.

**Tech Stack:** Python 3.12, stdlib only for new code (`sqlite3`, `re`, `pathlib`, `dataclasses`). YAML via existing `pyyaml` dep (already in project). FTS5 ships with stdlib `sqlite3`. No new external deps.

**Codex dispatch template** (use for every task):
```
/codex:rescue --model gpt-5.3-codex --wait

CONTEXT: <one paragraph — what slice of the wiki redesign this task ships, what came before>
SPEC: docs/superpowers/specs/2026-05-09-wiki-tools-redesign-design.md §<sections>
FILES TO CREATE: <exact paths>
FILES TO MODIFY: <exact paths with line refs>

TASK: <verbatim task body from this plan>

CONSTRAINTS:
- Senior engineer style: small focused functions, no dead code, no speculative abstraction
- TDD: write failing test first, run pytest, then implement, then re-run
- Match existing project patterns (see surrounding files)
- No new external deps
- pt-BR comments OK for prompt strings; all code/identifiers English
- Commit message: Conventional Commits format

VERIFICATION:
- All tests in this task pass
- `uv run ruff check <new files>` clean
- No print() in core/

REPORT BACK: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED), files changed, test count, commit SHA
```

---

## Wave 1 — Pure Foundation Modules (3 tasks in parallel)

No shared files. Dispatch all three in **one Agent message** with three concurrent codex calls.

### Task 1: Frontmatter parser

**Files:**
- Create: `src/conexus/core/memory/wiki/frontmatter.py`
- Test: `src/conexus/tests/core/memory/wiki/test_frontmatter.py`

**Spec refs:** §3.2, §6

- [ ] **Step 1: Write failing tests**

```python
# test_frontmatter.py
import pytest
from datetime import date
from conexus.core.memory.wiki.frontmatter import parse, inject, validate

def test_parse_no_frontmatter():
    meta, body = parse("# Hello\nworld")
    assert meta == {}
    assert body == "# Hello\nworld"

def test_parse_valid_frontmatter():
    text = "---\ncreated: 2026-05-09\ntags: [wiki]\nreviewed: false\n---\n# Body\n"
    meta, body = parse(text)
    assert meta["created"] == "2026-05-09"
    assert meta["tags"] == ["wiki"]
    assert meta["reviewed"] is False
    assert body == "# Body\n"

def test_parse_malformed_yaml_raises():
    with pytest.raises(ValueError):
        parse("---\n: : :\n---\nbody")

def test_inject_adds_when_missing():
    out = inject("# Body\n", {"created": "2026-05-09", "updated": "2026-05-09",
                                "tags": [], "source": "manual", "reviewed": False})
    meta, body = parse(out)
    assert meta["created"] == "2026-05-09"
    assert body == "# Body\n"

def test_inject_updates_updated_only():
    text = "---\ncreated: 2026-01-01\nupdated: 2026-01-01\nreviewed: true\n---\n# Body\n"
    out = inject(text, {"created": "ignored", "updated": "2026-05-09",
                        "tags": [], "source": "manual", "reviewed": False})
    meta, _ = parse(out)
    assert meta["created"] == "2026-01-01"   # never overwritten
    assert meta["updated"] == "2026-05-09"   # always set to provided
    assert meta["reviewed"] is True          # never overwritten

def test_validate_warns_missing_optional():
    warnings = validate({"created": "2026-05-09", "updated": "2026-05-09"})
    assert any("source" in w or "tags" in w for w in warnings)

def test_validate_hard_error_on_bad_reviewed():
    with pytest.raises(ValueError):
        validate({"created": "2026-05-09", "updated": "2026-05-09", "reviewed": "yes"})

def test_validate_hard_error_on_bad_date():
    with pytest.raises(ValueError):
        validate({"created": "yesterday", "updated": "2026-05-09", "reviewed": False})
```

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run pytest src/conexus/tests/core/memory/wiki/test_frontmatter.py -v
```
Expected: import error / module not found.

- [ ] **Step 3: Implement `frontmatter.py`**

```python
"""Wiki frontmatter — YAML between --- fences. Parse, inject defaults, validate."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import yaml

_FENCE_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Returns (meta, body). Empty meta if no frontmatter. Raises ValueError on malformed YAML."""
    m = _FENCE_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"malformed frontmatter YAML: {e}") from e
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return meta, m.group(2)


def inject(text: str, defaults: dict[str, Any]) -> str:
    """Add frontmatter if missing; update 'updated' field if present.
    Never overwrites 'created' or 'reviewed'."""
    meta, body = parse(text)
    if not meta:
        meta = dict(defaults)
    else:
        meta.setdefault("created", defaults.get("created"))
        meta.setdefault("tags", defaults.get("tags", []))
        meta.setdefault("source", defaults.get("source"))
        meta.setdefault("reviewed", defaults.get("reviewed", False))
        if "updated" in defaults:
            meta["updated"] = defaults["updated"]
    fm = yaml.safe_dump(meta, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{fm}\n---\n{body}"


def validate(meta: dict[str, Any]) -> list[str]:
    """Soft warnings list. Hard errors raise ValueError."""
    warnings: list[str] = []
    for required in ("created", "updated"):
        v = meta.get(required)
        if v is None:
            warnings.append(f"missing {required}")
        elif not isinstance(v, str) or not _ISO_DATE_RE.match(v):
            raise ValueError(f"{required} must be ISO date YYYY-MM-DD, got {v!r}")
    if "reviewed" in meta and not isinstance(meta["reviewed"], bool):
        raise ValueError(f"reviewed must be bool, got {type(meta['reviewed']).__name__}")
    if "tags" in meta and not isinstance(meta["tags"], list):
        raise ValueError("tags must be a list")
    if "source" not in meta:
        warnings.append("missing source")
    if "tags" not in meta:
        warnings.append("missing tags")
    return warnings


def today_iso() -> str:
    return date.today().isoformat()
```

- [ ] **Step 4: Re-run tests, verify pass**

- [ ] **Step 5: `/simplify` pass — review each function for senior-engineer terseness, remove any redundancy**

- [ ] **Step 6: Ruff check + commit**

```bash
uv run ruff check src/conexus/core/memory/wiki/frontmatter.py
git add src/conexus/core/memory/wiki/frontmatter.py src/conexus/tests/core/memory/wiki/test_frontmatter.py
git commit -m "feat(wiki): add frontmatter parser/injector/validator"
```

---

### Task 2: Markdown chunker

**Files:**
- Create: `src/conexus/core/memory/wiki/chunking.py`
- Test: `src/conexus/tests/core/memory/wiki/test_chunking.py`

**Spec refs:** §5

- [ ] **Step 1: Write failing tests**

```python
# test_chunking.py
from conexus.core.memory.wiki.chunking import markdown_chunks, Chunk

def test_no_headings_single_chunk():
    chunks = markdown_chunks("just plain text\nover two lines")
    assert len(chunks) == 1
    assert chunks[0].header_path == []
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 2

def test_split_by_h1_h2_h3():
    text = "# A\nintro\n## B\nbody\n### C\ndeep\n## D\nmore\n"
    chunks = markdown_chunks(text)
    paths = [c.header_path for c in chunks]
    assert ["# A"] in paths
    assert ["# A", "## B"] in paths
    assert ["# A", "## B", "### C"] in paths
    assert ["# A", "## D"] in paths

def test_frontmatter_excluded_from_chunks():
    text = "---\ncreated: 2026-05-09\n---\n# Heading\nbody\n"
    chunks = markdown_chunks(text)
    assert all("created:" not in c.body for c in chunks)
    assert chunks[0].header_path == ["# Heading"]
    assert chunks[0].line_start == 4   # after frontmatter

def test_oversized_section_recursive_split():
    big = "# H\n" + ("filler " * 1000)
    chunks = markdown_chunks(big, max_tokens=200, overlap_tokens=20)
    assert len(chunks) > 1
    for c in chunks:
        assert c.header_path == ["# H"]

def test_line_ranges_correct():
    text = "# A\nl2\nl3\n## B\nl5\n"
    chunks = markdown_chunks(text)
    a = next(c for c in chunks if c.header_path == ["# A"])
    assert a.line_start == 1 and a.line_end == 3
    b = next(c for c in chunks if c.header_path == ["# A", "## B"])
    assert b.line_start == 4 and b.line_end == 5

def test_empty_after_frontmatter_no_chunks():
    text = "---\ncreated: 2026-05-09\n---\n"
    chunks = markdown_chunks(text)
    assert chunks == []
```

- [ ] **Step 2: Run tests, verify failure**

- [ ] **Step 3: Implement `chunking.py`**

```python
"""Markdown-aware splitter. Sections by ATX heading (#, ##, ###).
Each chunk preserves header_path lineage. Oversized sections split with overlap."""
from __future__ import annotations

import re
from dataclasses import dataclass

from conexus.core.memory.wiki.frontmatter import parse

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")


@dataclass(frozen=True)
class Chunk:
    header_path: list[str]
    line_start: int
    line_end: int
    body: str


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _recursive_split(body: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    if _estimate_tokens(body) <= max_tokens:
        return [body]
    chars = max_tokens * 4
    overlap_chars = overlap_tokens * 4
    out: list[str] = []
    start = 0
    while start < len(body):
        end = min(len(body), start + chars)
        out.append(body[start:end])
        if end == len(body):
            break
        start = end - overlap_chars
    return out


def markdown_chunks(text: str, max_tokens: int = 800, overlap_tokens: int = 50) -> list[Chunk]:
    _, body = parse(text)
    body_offset = text.count("\n", 0, len(text) - len(body)) if body != text else 0

    lines = body.splitlines()
    if not lines:
        return []

    sections: list[tuple[list[str], int, int, list[str]]] = []
    stack: list[tuple[int, str]] = []  # (level, raw_heading)
    cur_start = 0
    cur_lines: list[str] = []

    def flush(end_idx: int) -> None:
        if not cur_lines:
            return
        path = [h for _, h in stack]
        sections.append((path, cur_start + 1 + body_offset, end_idx + body_offset, list(cur_lines)))

    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            flush(i)  # close previous section before this heading line
            level = len(m.group(1))
            stack = [(lv, h) for lv, h in stack if lv < level]
            stack.append((level, line.strip()))
            cur_start = i
            cur_lines = [line]
        else:
            cur_lines.append(line)
    flush(len(lines))

    chunks: list[Chunk] = []
    for header_path, start_line, end_line, sec_lines in sections:
        body_text = "\n".join(sec_lines)
        if not body_text.strip():
            continue
        if _estimate_tokens(body_text) <= max_tokens:
            chunks.append(Chunk(header_path, start_line, end_line, body_text))
        else:
            for piece in _recursive_split(body_text, max_tokens, overlap_tokens):
                chunks.append(Chunk(header_path, start_line, end_line, piece))
    return chunks
```

- [ ] **Step 4: Re-run tests, verify pass**

- [ ] **Step 5: `/simplify` pass**

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check src/conexus/core/memory/wiki/chunking.py
git add src/conexus/core/memory/wiki/chunking.py src/conexus/tests/core/memory/wiki/test_chunking.py
git commit -m "feat(wiki): add markdown-aware chunker with header_path metadata"
```

---

### Task 3: Citations module

**Files:**
- Create: `src/conexus/core/memory/wiki/citations.py`
- Test: `src/conexus/tests/core/memory/wiki/test_citations.py`

**Spec refs:** §9

- [ ] **Step 1: Write failing tests**

```python
# test_citations.py
from conexus.core.memory.wiki.citations import format_citation, parse_citations, slug_anchor

def test_slug_anchor_basic():
    assert slug_anchor("# Hello World") == "hello-world"
    assert slug_anchor("## Wiki Redesign — 2026") == "wiki-redesign-2026"

def test_format_citation():
    assert format_citation("notes.md", ["# Notes", "## Today"]) == "[notes.md#today]"

def test_parse_citations():
    text = "Conexus is in pt-BR [conventions.md#language] and uses [arch.md#wiki-layer]."
    cites = parse_citations(text)
    assert ("conventions.md", "language") in cites
    assert ("arch.md", "wiki-layer") in cites

def test_parse_citations_ignores_normal_links():
    text = "Visit [GitHub](https://github.com) for details."
    assert parse_citations(text) == []

def test_format_no_header_path_uses_filename():
    assert format_citation("readme.md", []) == "[readme.md]"
```

- [ ] **Step 2: Run tests, verify failure**

- [ ] **Step 3: Implement `citations.py`**

```python
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
    if not header_path:
        return f"[{path}]"
    return f"[{path}#{slug_anchor(header_path[-1])}]"


def parse_citations(text: str) -> list[tuple[str, str]]:
    """Returns list of (path, anchor) tuples; anchor is '' if absent."""
    return [(m.group(1), m.group(2) or "") for m in _CITATION_RE.finditer(text)]
```

- [ ] **Step 4: Re-run tests, verify pass**

- [ ] **Step 5: `/simplify` pass**

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check src/conexus/core/memory/wiki/citations.py
git add src/conexus/core/memory/wiki/citations.py src/conexus/tests/core/memory/wiki/test_citations.py
git commit -m "feat(wiki): add citation format/parse/slug helpers"
```

---

**Wave 1 review gate:** After all 3 tasks complete, dispatch one Opus reviewer with prompt:
> "Review commits for Tasks 1-3 in `docs/superpowers/plans/2026-05-09-wiki-tools-redesign.md`. Check spec compliance against §3.2/§5/§6/§9 of `docs/superpowers/specs/2026-05-09-wiki-tools-redesign-design.md`. Approve or list issues."

---

## Wave 2 — Schema Migration (1 task, sequential)

### Task 4: SQLite schema + helpers

**Files:**
- Modify: `src/conexus/core/memory/sqlite_store.py`
- Test: `src/conexus/tests/core/memory/test_sqlite_store_wiki.py` (NEW)

**Spec refs:** §3.1

- [ ] **Step 1: Write failing tests**

```python
# test_sqlite_store_wiki.py
from pathlib import Path
from conexus.core.memory.sqlite_store import SqliteStore

def _store(tmp_path: Path) -> SqliteStore:
    s = SqliteStore(str(tmp_path / "test.db"))
    s.init_db()
    return s

def test_wiki_pages_table_exists(tmp_path):
    s = _store(tmp_path)
    with s.conn as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wiki_pages'").fetchall()
    assert rows

def test_wiki_chunks_fts_exists(tmp_path):
    s = _store(tmp_path)
    with s.conn as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE name='wiki_chunks_fts'").fetchall()
    assert rows

def test_wiki_page_upsert_get(tmp_path):
    s = _store(tmp_path)
    s.wiki_page_set("agent1", "notes.md", mtime_ns=123, created="2026-05-09",
                    updated="2026-05-09", tags=["a"], source="test", reviewed=False)
    row = s.wiki_page_get("agent1", "notes.md")
    assert row["mtime_ns"] == 123
    assert row["tags"] == ["a"]
    assert row["reviewed"] is False

def test_wiki_page_delete_cascades_chunks(tmp_path):
    s = _store(tmp_path)
    s.wiki_page_set("agent1", "n.md", mtime_ns=1, created=None, updated=None,
                    tags=[], source=None, reviewed=False)
    s.wiki_chunk_insert("agent1", "n.md", header_path=["# H"],
                        line_start=1, line_end=2, body="hello world")
    s.wiki_page_delete("agent1", "n.md")
    with s.conn as c:
        chunks = c.execute("SELECT * FROM wiki_chunks WHERE path='n.md'").fetchall()
    assert chunks == []

def test_fts_search_round_trip(tmp_path):
    s = _store(tmp_path)
    s.wiki_page_set("agent1", "n.md", mtime_ns=1, created=None, updated=None,
                    tags=[], source=None, reviewed=False)
    s.wiki_chunk_insert("agent1", "n.md", header_path=["# H"],
                        line_start=1, line_end=2, body="alpha beta gamma")
    hits = s.wiki_fts_search("agent1", "beta", k=5)
    assert len(hits) == 1
    assert hits[0]["path"] == "n.md"

def test_fts_diacritic_insensitive(tmp_path):
    s = _store(tmp_path)
    s.wiki_page_set("agent1", "n.md", mtime_ns=1, created=None, updated=None,
                    tags=[], source=None, reviewed=False)
    s.wiki_chunk_insert("agent1", "n.md", header_path=["# H"],
                        line_start=1, line_end=2, body="café com leite")
    assert len(s.wiki_fts_search("agent1", "cafe", k=5)) == 1

def test_per_agent_isolation(tmp_path):
    s = _store(tmp_path)
    for a in ("a1", "a2"):
        s.wiki_page_set(a, "n.md", mtime_ns=1, created=None, updated=None,
                        tags=[], source=None, reviewed=False)
        s.wiki_chunk_insert(a, "n.md", header_path=["# H"],
                            line_start=1, line_end=2, body=f"hello from {a}")
    a1_hits = s.wiki_fts_search("a1", "hello", k=5)
    assert len(a1_hits) == 1 and "a1" in a1_hits[0]["snippet"]
```

- [ ] **Step 2: Run tests, verify failure**

- [ ] **Step 3: Add tables + triggers + helpers to `sqlite_store.py`**

Locate the `init_db` method and append after existing tables (before `pack_migrations`):

```python
# --- wiki redesign (Phase 3) ---
c.execute("""
CREATE TABLE IF NOT EXISTS wiki_pages (
    agent_id  TEXT NOT NULL,
    path      TEXT NOT NULL,
    mtime_ns  INTEGER NOT NULL,
    created   TEXT,
    updated   TEXT,
    tags      TEXT,
    source    TEXT,
    reviewed  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (agent_id, path)
)""")
c.execute("""
CREATE TABLE IF NOT EXISTS wiki_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    path        TEXT NOT NULL,
    header_path TEXT NOT NULL,
    line_start  INTEGER NOT NULL,
    line_end    INTEGER NOT NULL,
    body        TEXT NOT NULL
)""")
c.execute("CREATE INDEX IF NOT EXISTS wiki_chunks_path ON wiki_chunks(agent_id, path)")
c.execute("""
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_chunks_fts USING fts5(
    body,
    content='wiki_chunks',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
)""")
c.execute("""
CREATE TRIGGER IF NOT EXISTS wiki_chunks_ai AFTER INSERT ON wiki_chunks BEGIN
    INSERT INTO wiki_chunks_fts(rowid, body) VALUES (new.id, new.body);
END""")
c.execute("""
CREATE TRIGGER IF NOT EXISTS wiki_chunks_ad AFTER DELETE ON wiki_chunks BEGIN
    INSERT INTO wiki_chunks_fts(wiki_chunks_fts, rowid, body) VALUES ('delete', old.id, old.body);
END""")
c.execute("""
CREATE TRIGGER IF NOT EXISTS wiki_chunks_au AFTER UPDATE ON wiki_chunks BEGIN
    INSERT INTO wiki_chunks_fts(wiki_chunks_fts, rowid, body) VALUES ('delete', old.id, old.body);
    INSERT INTO wiki_chunks_fts(rowid, body) VALUES (new.id, new.body);
END""")
```

Add helpers as new methods on `SqliteStore`:

```python
import json

def wiki_page_set(self, agent_id: str, path: str, *, mtime_ns: int,
                  created: str | None, updated: str | None,
                  tags: list[str], source: str | None, reviewed: bool) -> None:
    with self.conn as c:
        c.execute("""
            INSERT INTO wiki_pages (agent_id, path, mtime_ns, created, updated, tags, source, reviewed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id, path) DO UPDATE SET
                mtime_ns=excluded.mtime_ns, created=excluded.created,
                updated=excluded.updated, tags=excluded.tags,
                source=excluded.source, reviewed=excluded.reviewed
        """, (agent_id, path, mtime_ns, created, updated, json.dumps(tags), source, int(reviewed)))

def wiki_page_get(self, agent_id: str, path: str) -> dict | None:
    with self.conn as c:
        row = c.execute("""
            SELECT path, mtime_ns, created, updated, tags, source, reviewed
            FROM wiki_pages WHERE agent_id=? AND path=?
        """, (agent_id, path)).fetchone()
    if not row:
        return None
    return {"path": row[0], "mtime_ns": row[1], "created": row[2], "updated": row[3],
            "tags": json.loads(row[4] or "[]"), "source": row[5], "reviewed": bool(row[6])}

def wiki_page_list(self, agent_id: str) -> list[dict]:
    with self.conn as c:
        rows = c.execute("""
            SELECT path, mtime_ns, created, updated, tags, source, reviewed
            FROM wiki_pages WHERE agent_id=?
        """, (agent_id,)).fetchall()
    return [{"path": r[0], "mtime_ns": r[1], "created": r[2], "updated": r[3],
             "tags": json.loads(r[4] or "[]"), "source": r[5], "reviewed": bool(r[6])} for r in rows]

def wiki_page_delete(self, agent_id: str, path: str) -> None:
    with self.conn as c:
        c.execute("DELETE FROM wiki_chunks WHERE agent_id=? AND path=?", (agent_id, path))
        c.execute("DELETE FROM wiki_pages WHERE agent_id=? AND path=?", (agent_id, path))

def wiki_chunks_clear(self, agent_id: str, path: str) -> None:
    with self.conn as c:
        c.execute("DELETE FROM wiki_chunks WHERE agent_id=? AND path=?", (agent_id, path))

def wiki_chunk_insert(self, agent_id: str, path: str, *, header_path: list[str],
                      line_start: int, line_end: int, body: str) -> int:
    with self.conn as c:
        cur = c.execute("""
            INSERT INTO wiki_chunks (agent_id, path, header_path, line_start, line_end, body)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (agent_id, path, json.dumps(header_path), line_start, line_end, body))
        return cur.lastrowid

def wiki_fts_search(self, agent_id: str, query: str, k: int = 10) -> list[dict]:
    with self.conn as c:
        rows = c.execute("""
            SELECT wc.path, wc.header_path, wc.line_start, wc.line_end,
                   snippet(wiki_chunks_fts, 0, '<mark>', '</mark>', '...', 32) AS snippet,
                   bm25(wiki_chunks_fts) AS rank
            FROM wiki_chunks_fts
            JOIN wiki_chunks wc ON wc.id = wiki_chunks_fts.rowid
            WHERE wiki_chunks_fts MATCH ? AND wc.agent_id = ?
            ORDER BY rank LIMIT ?
        """, (query, agent_id, k)).fetchall()
    return [{"path": r[0], "header_path": json.loads(r[1]), "line_start": r[2],
             "line_end": r[3], "snippet": r[4], "score": float(r[5])} for r in rows]
```

- [ ] **Step 4: Re-run tests, verify pass**

- [ ] **Step 5: `/simplify` — review for any redundant SQL or duplicated patterns**

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check src/conexus/core/memory/sqlite_store.py
git add src/conexus/core/memory/sqlite_store.py src/conexus/tests/core/memory/test_sqlite_store_wiki.py
git commit -m "feat(store): add wiki_pages/wiki_chunks/wiki_chunks_fts schema + helpers"
```

---

## Wave 3 — Index Layer (1 task, sequential)

### Task 5: WikiIndex protocol + SqliteFtsIndex impl

**Files:**
- Create: `src/conexus/core/memory/wiki/index.py`
- Create: `src/conexus/core/memory/wiki/index_sqlite.py`
- Test: `src/conexus/tests/core/memory/wiki/test_index_sqlite.py`

**Spec refs:** §4

- [ ] **Step 1: Write failing tests**

```python
# test_index_sqlite.py
from pathlib import Path
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex
from conexus.core.memory.wiki.local import LocalBackend

def _setup(tmp_path: Path):
    store = SqliteStore(str(tmp_path / "t.db")); store.init_db()
    backend = LocalBackend(tmp_path / "wiki")
    idx = SqliteFtsIndex(store=store, agent_id="a1", backend=backend)
    return store, backend, idx

def test_reindex_path_inserts_chunks(tmp_path):
    store, backend, idx = _setup(tmp_path)
    backend.write("notes.md", "---\ncreated: 2026-05-09\nupdated: 2026-05-09\nreviewed: false\n---\n# H\nbody alpha\n")
    p = (tmp_path / "wiki" / "notes.md").resolve()
    idx.reindex_path("notes.md", backend.read("notes.md"), p.stat().st_mtime_ns)
    hits = idx.search("alpha")
    assert hits and hits[0].path == "notes.md"
    assert hits[0].header_path == ["# H"]

def test_reconcile_drops_missing(tmp_path):
    store, backend, idx = _setup(tmp_path)
    backend.write("a.md", "# A\nalpha\n")
    p = (tmp_path / "wiki" / "a.md").resolve()
    idx.reindex_path("a.md", backend.read("a.md"), p.stat().st_mtime_ns)
    idx.reconcile({})  # path no longer present
    assert idx.search("alpha") == []

def test_reconcile_reindexes_stale(tmp_path):
    store, backend, idx = _setup(tmp_path)
    backend.write("a.md", "# A\nalpha\n")
    p = (tmp_path / "wiki" / "a.md").resolve()
    idx.reindex_path("a.md", backend.read("a.md"), 1)  # stored mtime=1
    backend.write("a.md", "# A\nbeta\n")
    new_mt = p.stat().st_mtime_ns
    idx.reconcile({"a.md": new_mt})
    hits_a = idx.search("alpha")
    hits_b = idx.search("beta")
    assert hits_a == []
    assert hits_b and hits_b[0].path == "a.md"

def test_drop_path(tmp_path):
    store, backend, idx = _setup(tmp_path)
    backend.write("a.md", "# A\nalpha\n")
    p = (tmp_path / "wiki" / "a.md").resolve()
    idx.reindex_path("a.md", backend.read("a.md"), p.stat().st_mtime_ns)
    idx.drop_path("a.md")
    assert idx.search("alpha") == []

def test_page_meta_after_reindex(tmp_path):
    store, backend, idx = _setup(tmp_path)
    backend.write("a.md", "---\ncreated: 2026-05-09\nupdated: 2026-05-09\ntags: [x]\nreviewed: false\n---\n# A\nalpha\n")
    p = (tmp_path / "wiki" / "a.md").resolve()
    idx.reindex_path("a.md", backend.read("a.md"), p.stat().st_mtime_ns)
    meta = idx.page_meta("a.md")
    assert meta is not None
    assert meta.tags == ["x"]
```

- [ ] **Step 2: Run tests, verify failure**

- [ ] **Step 3: Implement `index.py` (Protocol + dataclasses)**

```python
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
```

- [ ] **Step 4: Implement `index_sqlite.py`**

```python
"""SQLite FTS5 implementation of WikiIndex. Mtime-reconciled cache over WikiBackend."""
from __future__ import annotations

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.backend import WikiBackend
from conexus.core.memory.wiki.chunking import markdown_chunks
from conexus.core.memory.wiki.frontmatter import parse as parse_frontmatter
from conexus.core.memory.wiki.index import PageMeta, SearchHit, WikiIndex


class SqliteFtsIndex(WikiIndex):
    def __init__(self, *, store: SqliteStore, agent_id: str, backend: WikiBackend) -> None:
        self._store = store
        self._agent_id = agent_id
        self._backend = backend

    def reindex_path(self, path: str, content: str, mtime_ns: int) -> None:
        meta, _ = parse_frontmatter(content)
        self._store.wiki_page_set(
            self._agent_id, path,
            mtime_ns=mtime_ns,
            created=meta.get("created"),
            updated=meta.get("updated"),
            tags=meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
            source=meta.get("source"),
            reviewed=bool(meta.get("reviewed", False)),
        )
        self._store.wiki_chunks_clear(self._agent_id, path)
        for ch in markdown_chunks(content):
            self._store.wiki_chunk_insert(
                self._agent_id, path,
                header_path=ch.header_path,
                line_start=ch.line_start, line_end=ch.line_end,
                body=ch.body,
            )

    def drop_path(self, path: str) -> None:
        self._store.wiki_page_delete(self._agent_id, path)

    def reconcile(self, paths: dict[str, int]) -> None:
        stored = {p["path"]: p["mtime_ns"] for p in self._store.wiki_page_list(self._agent_id)}
        for path, mt in paths.items():
            if stored.get(path, -1) < mt:
                content = self._backend.read(path)
                self._reindex_from_backend(path, content)
        for path in stored.keys() - paths.keys():
            self.drop_path(path)

    def _reindex_from_backend(self, path: str, content: str) -> None:
        # backend may not expose mtime; ask via raw filesystem when possible
        try:
            from pathlib import Path as _P
            p = _P(getattr(self._backend, "root", _P("."))) / path
            mtime_ns = p.stat().st_mtime_ns
        except Exception:
            mtime_ns = 0
        self.reindex_path(path, content, mtime_ns)

    def search(self, query: str, k: int = 10) -> list[SearchHit]:
        rows = self._store.wiki_fts_search(self._agent_id, query, k=k)
        return [SearchHit(
            path=r["path"], header_path=r["header_path"], snippet=r["snippet"],
            score=r["score"], line_start=r["line_start"], line_end=r["line_end"],
        ) for r in rows]

    def page_meta(self, path: str) -> PageMeta | None:
        row = self._store.wiki_page_get(self._agent_id, path)
        if row is None:
            return None
        return PageMeta(path=row["path"], mtime_ns=row["mtime_ns"], created=row["created"],
                        updated=row["updated"], tags=row["tags"], source=row["source"],
                        reviewed=row["reviewed"])

    def all_pages(self) -> list[PageMeta]:
        return [PageMeta(path=r["path"], mtime_ns=r["mtime_ns"], created=r["created"],
                         updated=r["updated"], tags=r["tags"], source=r["source"],
                         reviewed=r["reviewed"]) for r in self._store.wiki_page_list(self._agent_id)]
```

- [ ] **Step 5: Re-run tests, verify pass**

- [ ] **Step 6: `/simplify`**

- [ ] **Step 7: Ruff + commit**

```bash
uv run ruff check src/conexus/core/memory/wiki/index.py src/conexus/core/memory/wiki/index_sqlite.py
git add src/conexus/core/memory/wiki/index.py src/conexus/core/memory/wiki/index_sqlite.py src/conexus/tests/core/memory/wiki/test_index_sqlite.py
git commit -m "feat(wiki): SqliteFtsIndex with mtime reconciliation"
```

---

## Wave 4 — Composition Layer (2 tasks in parallel)

Different files, no shared state. Dispatch both in **one Agent message** with two concurrent codex calls.

### Task 6: WikiStore enhancement

**Files:**
- Modify: `src/conexus/core/memory/wiki_store.py`
- Modify: `src/conexus/core/memory/wiki/__init__.py` (export new symbols)
- Test: `src/conexus/tests/core/memory/wiki/test_wiki_store_indexed.py` (NEW)

**Spec refs:** §2, §6, §7 partial

- [ ] **Step 1: Write failing tests**

```python
# test_wiki_store_indexed.py
from pathlib import Path
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.local import LocalBackend
from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex
from conexus.core.memory.wiki_store import WikiStore

def _make(tmp_path: Path) -> WikiStore:
    store = SqliteStore(str(tmp_path / "t.db")); store.init_db()
    backend = LocalBackend(tmp_path / "wiki")
    idx = SqliteFtsIndex(store=store, agent_id="a", backend=backend)
    return WikiStore(backend, index=idx)

def test_write_injects_frontmatter_and_indexes(tmp_path):
    ws = _make(tmp_path)
    out = ws.write("a.md", "# Hello\nworld alpha")
    assert out["ok"] is True
    raw = ws.read("a.md")
    assert raw.startswith("---\n")
    hits = ws.search("alpha")
    assert hits and hits[0]["path"] == "a.md"

def test_search_after_external_modification(tmp_path):
    ws = _make(tmp_path)
    ws.write("a.md", "# A\nfoo")
    # external edit
    (tmp_path / "wiki" / "a.md").write_text(
        "---\ncreated: 2026-05-09\nupdated: 2026-05-09\nreviewed: false\n---\n# A\nbar\n")
    hits_foo = ws.search("foo")
    hits_bar = ws.search("bar")
    assert hits_foo == []
    assert hits_bar and hits_bar[0]["path"] == "a.md"

def test_delete_drops_from_index(tmp_path):
    ws = _make(tmp_path)
    ws.write("a.md", "# A\nalpha")
    ws.delete("a.md")
    assert ws.search("alpha") == []

def test_exists(tmp_path):
    ws = _make(tmp_path)
    assert ws.exists("a.md") is False
    ws.write("a.md", "# A\nbody")
    assert ws.exists("a.md") is True

def test_move_with_backlink_update(tmp_path):
    ws = _make(tmp_path)
    ws.write("target.md", "# T\ncontent")
    ws.write("ref.md", "# R\nsee [target.md#t] for details")
    res = ws.move("target.md", "renamed.md")
    assert res["ok"] is True
    assert res["backlinks_updated"] == 1
    assert "renamed.md" in ws.read("ref.md")

def test_legacy_no_index(tmp_path):
    backend = LocalBackend(tmp_path / "wiki")
    ws = WikiStore(backend)  # no index — legacy mode
    ws.write("a.md", "# A\nalpha")
    hits = ws.search("alpha")
    assert hits and hits[0]["path"] == "a.md"
```

- [ ] **Step 2: Run tests, verify failure**

- [ ] **Step 3: Rewrite `wiki_store.py`**

```python
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
    def __init__(self, backend_or_root: WikiBackend | str | Path,
                 index: WikiIndex | None = None) -> None:
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
        defaults = {"created": today_iso(), "updated": today_iso(),
                    "tags": [], "source": None, "reviewed": False}
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
        return {"ok": True, "src": src, "dst": dst, "backlinks_updated": backlinks_updated}

    # ----- search -----

    def search(self, query: str, k: int = 10) -> list[dict]:
        if self._index is None:
            return self._backend.search(query)
        self._reconcile()
        hits = self._index.search(query, k=k)
        return [{"path": h.path, "header_path": h.header_path, "snippet": h.snippet,
                 "score": h.score, "line_start": h.line_start, "line_end": h.line_end}
                for h in hits]

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
        lines.append(f"- [{label}]({path}) — {summary} ({date_str})")
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
        count = 0
        for rel in self._backend.list():
            text = self._backend.read(rel)
            new = pat.sub(rf"[\1]({dst}\2)", text)
            new = wikilink.sub(rf"[[{dst}\1]]", new)
            if new != text:
                self._backend.write(rel, new)
                if self._index:
                    self._index.reindex_path(rel, new, self._mtime_ns(rel))
                count += 1
        return count
```

Update `wiki/__init__.py`:

```python
from conexus.core.memory.wiki.backend import WikiBackend, safe_join
from conexus.core.memory.wiki.github_app import GitHubAppBackend
from conexus.core.memory.wiki.index import PageMeta, SearchHit, WikiIndex
from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex
from conexus.core.memory.wiki.local import LocalBackend

__all__ = [
    "GitHubAppBackend", "LocalBackend", "PageMeta", "SearchHit",
    "SqliteFtsIndex", "WikiBackend", "WikiIndex", "safe_join",
]
```

- [ ] **Step 4: Re-run tests, verify pass**

- [ ] **Step 5: `/simplify`**

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check src/conexus/core/memory/wiki_store.py src/conexus/core/memory/wiki/__init__.py
git add src/conexus/core/memory/wiki_store.py src/conexus/core/memory/wiki/__init__.py src/conexus/tests/core/memory/wiki/test_wiki_store_indexed.py
git commit -m "feat(wiki): WikiStore composes index, frontmatter discipline on write, move with backlink update"
```

---

### Task 7: Lint module

**Files:**
- Create: `src/conexus/core/memory/wiki/lint.py`
- Test: `src/conexus/tests/core/memory/wiki/test_lint.py`

**Spec refs:** §8

- [ ] **Step 1: Write failing tests**

```python
# test_lint.py
from pathlib import Path
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.local import LocalBackend
from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex
from conexus.core.memory.wiki.lint import lint_wiki
from conexus.core.memory.wiki_store import WikiStore

def _ws(tmp_path: Path) -> WikiStore:
    s = SqliteStore(str(tmp_path / "t.db")); s.init_db()
    b = LocalBackend(tmp_path / "wiki")
    return WikiStore(b, index=SqliteFtsIndex(store=s, agent_id="a", backend=b))

def test_orphan_detection(tmp_path):
    ws = _ws(tmp_path)
    ws.write("orphan.md", "# Orphan\nbody")
    ws.write("index.md", "# Index\n- [other](other.md) — placeholder")
    ws.write("other.md", "# Other\nbody")
    report = lint_wiki(ws)
    assert "orphan.md" in report.orphans

def test_dead_link_detection(tmp_path):
    ws = _ws(tmp_path)
    ws.write("a.md", "# A\nsee [b.md#h] which does not exist")
    report = lint_wiki(ws)
    assert ("a.md", "b.md") in report.dead_links

def test_missing_frontmatter_flagged(tmp_path):
    ws = _ws(tmp_path)
    # write directly via backend bypassing inject
    (tmp_path / "wiki").mkdir(exist_ok=True)
    (tmp_path / "wiki" / "raw.md").write_text("# Raw\nno frontmatter\n")
    report = lint_wiki(ws)
    assert "raw.md" in report.missing_frontmatter

def test_stub_pages_under_threshold(tmp_path):
    ws = _ws(tmp_path)
    ws.write("stub.md", "# S\nx")
    report = lint_wiki(ws)
    assert "stub.md" in report.stub_pages

def test_stale_index_entries(tmp_path):
    ws = _ws(tmp_path)
    ws.write("index.md", "# Index\n- [missing](missing.md) — stale")
    report = lint_wiki(ws)
    assert "missing.md" in report.stale_index

def test_total_issues_property(tmp_path):
    ws = _ws(tmp_path)
    ws.write("stub.md", "# S\nx")
    report = lint_wiki(ws)
    assert report.total_issues > 0
```

- [ ] **Step 2: Run tests, verify failure**

- [ ] **Step 3: Implement `lint.py`**

```python
"""Wiki health checks. Read-only — never modifies files."""
from __future__ import annotations

import re
from dataclasses import dataclass

from conexus.core.memory.wiki.frontmatter import parse


_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
_INDEX_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)\)")
_STUB_THRESHOLD_CHARS = 200


@dataclass(frozen=True)
class LintReport:
    orphans: list[str]
    dead_links: list[tuple[str, str]]
    missing_frontmatter: list[str]
    stub_pages: list[str]
    stale_index: list[str]

    @property
    def total_issues(self) -> int:
        return (len(self.orphans) + len(self.dead_links)
                + len(self.missing_frontmatter) + len(self.stub_pages) + len(self.stale_index))


def lint_wiki(store) -> LintReport:
    backend = store.backend
    paths = set(backend.list())

    # parse index.md once
    index_targets: set[str] = set()
    if "index.md" in paths:
        for m in _INDEX_LINK_RE.finditer(backend.read("index.md")):
            index_targets.add(m.group(1))

    orphans: list[str] = []
    dead_links: list[tuple[str, str]] = []
    missing_fm: list[str] = []
    stubs: list[str] = []

    for p in sorted(paths):
        if p in {"index.md", "log.md"}:
            continue
        text = backend.read(p)
        try:
            meta, body = parse(text)
        except ValueError:
            missing_fm.append(p); continue
        if not meta:
            missing_fm.append(p)
        if len(body.strip()) < _STUB_THRESHOLD_CHARS:
            stubs.append(p)
        if p not in index_targets:
            orphans.append(p)
        for m in _LINK_RE.finditer(body):
            target = m.group(1)
            if target not in paths:
                dead_links.append((p, target))

    stale_index = sorted(t for t in index_targets if t not in paths)
    return LintReport(orphans=orphans, dead_links=dead_links,
                      missing_frontmatter=missing_fm, stub_pages=stubs,
                      stale_index=stale_index)
```

- [ ] **Step 4: Re-run tests, verify pass**

- [ ] **Step 5: `/simplify`**

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check src/conexus/core/memory/wiki/lint.py
git add src/conexus/core/memory/wiki/lint.py src/conexus/tests/core/memory/wiki/test_lint.py
git commit -m "feat(wiki): add lint_wiki — orphans/dead_links/missing_fm/stubs/stale_index"
```

---

**Wave 4 review gate:** Spec compliance review against §6/§7/§8. Approve before Wave 5.

---

## Wave 5 — Wiring (2 tasks in parallel)

Different files. Dispatch both in **one Agent message**.

### Task 8: Identity tools expansion

**Files:**
- Modify: `src/conexus/core/identity/tools.py`
- Test: `src/conexus/tests/core/identity/test_tools_wiki.py` (NEW)

**Spec refs:** §7

- [ ] **Step 1: Write failing tests**

```python
# test_tools_wiki.py
from pathlib import Path
from conexus.core.identity.blocks import BlockStore
from conexus.core.identity.tools import IdentityTools
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex
from conexus.core.memory.wiki.local import LocalBackend
from conexus.core.memory.wiki_store import WikiStore

def _tools(tmp_path: Path) -> IdentityTools:
    s = SqliteStore(str(tmp_path / "t.db")); s.init_db()
    b = LocalBackend(tmp_path / "wiki")
    idx = SqliteFtsIndex(store=s, agent_id="a", backend=b)
    ws = WikiStore(b, index=idx)
    return IdentityTools(agent_id="a", store=s, wiki=ws,
                         blocks=BlockStore(s), block_specs={})

def test_wiki_exists_returns_bool(tmp_path):
    t = _tools(tmp_path)
    assert t.wiki_exists("a.md") is False
    t.wiki_write("a.md", "# A\nbody")
    assert t.wiki_exists("a.md") is True

def test_wiki_delete_returns_ok(tmp_path):
    t = _tools(tmp_path)
    t.wiki_write("a.md", "# A\nbody")
    res = t.wiki_delete("a.md")
    assert res == {"ok": True, "path": "a.md"}
    assert t.wiki_exists("a.md") is False

def test_wiki_move(tmp_path):
    t = _tools(tmp_path)
    t.wiki_write("a.md", "# A\nbody")
    t.wiki_write("ref.md", "# R\nsee [a.md#a]")
    res = t.wiki_move("a.md", "b.md")
    assert res["ok"] is True
    assert res["backlinks_updated"] == 1

def test_wiki_lint_returns_dict(tmp_path):
    t = _tools(tmp_path)
    t.wiki_write("stub.md", "# S\nx")
    res = t.wiki_lint()
    assert "orphans" in res and "dead_links" in res
    assert "stub.md" in res["stub_pages"]

def test_wiki_index_update(tmp_path):
    t = _tools(tmp_path)
    t.wiki_write("note.md", "# N\nbody")
    res = t.wiki_index_update("note.md", "a note about things")
    assert res == {"ok": True}
    assert "note.md" in t.wiki_read("index.md")
```

- [ ] **Step 2: Run tests, verify failure**

- [ ] **Step 3: Add tools to `identity/tools.py`**

Append to `IdentityTools` class:

```python
def wiki_delete(self, path: str) -> dict:
    return self._require_wiki().delete(path)

def wiki_exists(self, path: str) -> bool:
    return self._require_wiki().exists(path)

def wiki_move(self, src: str, dst: str) -> dict:
    return self._require_wiki().move(src, dst)

def wiki_lint(self) -> dict:
    from conexus.core.memory.wiki.lint import lint_wiki
    r = lint_wiki(self._require_wiki())
    return {"orphans": r.orphans, "dead_links": [list(t) for t in r.dead_links],
            "missing_frontmatter": r.missing_frontmatter, "stub_pages": r.stub_pages,
            "stale_index": r.stale_index, "total_issues": r.total_issues}

def wiki_index_update(self, path: str, summary: str) -> dict:
    self._require_wiki().update_index(path, summary)
    return {"ok": True}
```

Update `wiki_search` to pass through new shape (already handled by WikiStore — verify return type doc string updated).

Update module docstring tool list at top to include the 5 new tools.

- [ ] **Step 4: Re-run tests, verify pass**

- [ ] **Step 5: `/simplify`**

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check src/conexus/core/identity/tools.py
git add src/conexus/core/identity/tools.py src/conexus/tests/core/identity/test_tools_wiki.py
git commit -m "feat(identity): expose wiki_delete/exists/move/lint/index_update tools"
```

---

### Task 9: Identity runtime wiring

**Files:**
- Modify: `src/conexus/cli/identity_runtime.py`
- Test: `src/conexus/tests/cli/test_identity_runtime_wiki.py` (NEW)

**Spec refs:** §2 (composition)

- [ ] **Step 1: Write failing test**

```python
# test_identity_runtime_wiki.py
from pathlib import Path
from conexus.cli.identity_runtime import _build_wiki
from conexus.core.config.skill_loader import WikiSection
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.index import WikiIndex

def test_build_wiki_local_attaches_index(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db")); store.init_db()
    skill_dir = tmp_path / "agent"
    skill_dir.mkdir()
    cfg = WikiSection(backend="local", dir="wiki", inject_index=False)
    ws = _build_wiki(cfg, skill_dir, agent_id="a", store=store)
    assert ws.index is not None
    assert isinstance(ws.index, WikiIndex)

def test_build_wiki_search_works_round_trip(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db")); store.init_db()
    skill_dir = tmp_path / "agent"
    skill_dir.mkdir()
    cfg = WikiSection(backend="local", dir="wiki", inject_index=False)
    ws = _build_wiki(cfg, skill_dir, agent_id="a", store=store)
    ws.write("a.md", "# A\nalpha beta")
    hits = ws.search("alpha")
    assert hits and hits[0]["path"] == "a.md"
```

- [ ] **Step 2: Run test, verify failure**

- [ ] **Step 3: Modify `_build_wiki` to attach `SqliteFtsIndex`**

In `identity_runtime.py`, modify the `local` branch and `github_app` branch of `_build_wiki` to construct an index:

```python
from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex

def _build_wiki(wiki_cfg: WikiSection, skill_dir: Path, *,
                agent_id: str = "", store: SqliteStore | None = None) -> WikiStore:
    if wiki_cfg.backend == "local":
        backend = LocalBackend(skill_dir / wiki_cfg.dir)
        idx = SqliteFtsIndex(store=store, agent_id=agent_id, backend=backend) if store and agent_id else None
        return WikiStore(backend, index=idx)
    if wiki_cfg.backend == "github_app":
        if store is None or not agent_id:
            raise RuntimeError("github_app backend requires store + agent_id")
        row = store.github_app_install_get(agent_id)
        if row is None:
            raise RuntimeError(f"Agent '{agent_id}' github wiki not connected. "
                               "Visit /admin/oauth/github/start to install the app.")
        backend = GitHubAppBackend(
            local_root=skill_dir / wiki_cfg.dir,
            repo_slug=row["repo_slug"],
            installation_id=row["installation_id"],
            app_id=os.environ["GITHUB_APP_ID"],
            private_key_pem=os.environ["GITHUB_APP_PRIVATE_KEY"],
        )
        idx = SqliteFtsIndex(store=store, agent_id=agent_id, backend=backend)
        return WikiStore(backend, index=idx)
    raise ValueError(f"unknown wiki backend: {wiki_cfg.backend!r}")
```

- [ ] **Step 4: Re-run tests, verify pass; also re-run existing identity tests to confirm no regression**

```bash
uv run pytest src/conexus/tests/cli/ -v
```

- [ ] **Step 5: `/simplify`**

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check src/conexus/cli/identity_runtime.py
git add src/conexus/cli/identity_runtime.py src/conexus/tests/cli/test_identity_runtime_wiki.py
git commit -m "feat(runtime): wire SqliteFtsIndex into _build_wiki for local + github_app"
```

---

**Wave 5 review gate:** Spec compliance against §2/§7. Approve before Wave 6.

---

## Wave 6 — Migration + Prompt (2 tasks in parallel)

Different files. Dispatch both in **one Agent message**.

### Task 10: Migration CLI subcommand

**Files:**
- Create: `src/conexus/cli/wiki_migrate.py`
- Modify: `src/conexus/cli/__main__.py` (register subcommand)
- Test: `src/conexus/tests/cli/test_wiki_migrate.py` (NEW)

**Spec refs:** §10

- [ ] **Step 1: Write failing test**

```python
# test_wiki_migrate.py
from pathlib import Path
from conexus.cli.wiki_migrate import migrate_agent_wiki
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.local import LocalBackend

def test_migrate_injects_frontmatter_and_indexes(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "a.md").write_text("# A\nalpha\n")
    (wiki / "b.md").write_text("---\ncreated: 2025-01-01\nupdated: 2025-01-01\nreviewed: false\n---\n# B\nbeta\n")
    store = SqliteStore(str(tmp_path / "t.db")); store.init_db()
    backend = LocalBackend(wiki)
    result = migrate_agent_wiki(agent_id="a", backend=backend, store=store)
    assert result["pages_processed"] == 2
    assert result["frontmatter_injected"] == 1
    a_meta = store.wiki_page_get("a", "a.md")
    assert a_meta["created"] is not None

def test_migrate_idempotent(tmp_path):
    wiki = tmp_path / "wiki"; wiki.mkdir()
    (wiki / "a.md").write_text("# A\nbody\n")
    store = SqliteStore(str(tmp_path / "t.db")); store.init_db()
    backend = LocalBackend(wiki)
    r1 = migrate_agent_wiki("a", backend, store)
    r2 = migrate_agent_wiki("a", backend, store)
    assert r1["frontmatter_injected"] == 1
    assert r2["frontmatter_injected"] == 0
```

- [ ] **Step 2: Run test, verify failure**

- [ ] **Step 3: Implement `wiki_migrate.py`**

```python
"""One-shot migration: inject frontmatter where missing + build initial FTS index."""
from __future__ import annotations

from datetime import date

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
```

- [ ] **Step 4: Register `wiki migrate` subcommand in `__main__.py`**

Add to existing argparse subcommand setup:

```python
sub_wiki = subparsers.add_parser("wiki", help="wiki maintenance")
wiki_sub = sub_wiki.add_subparsers(dest="wiki_cmd")
mig = wiki_sub.add_parser("migrate", help="inject frontmatter + build FTS index")
mig.add_argument("--agent", required=True)
mig.add_argument("--data-dir", default="./data")
mig.add_argument("--agents-dir", default="./agents")
```

And in the dispatch:

```python
if args.cmd == "wiki" and args.wiki_cmd == "migrate":
    from conexus.cli.wiki_migrate import migrate_agent_wiki
    from conexus.core.memory.sqlite_store import SqliteStore
    from conexus.core.memory.wiki.local import LocalBackend
    from pathlib import Path
    store = SqliteStore(f"{args.data_dir}/conexus.db"); store.init_db()
    backend = LocalBackend(Path(args.agents_dir) / args.agent / "wiki")
    res = migrate_agent_wiki(args.agent, backend, store)
    print(res)
    return 0
```

- [ ] **Step 5: Re-run tests, verify pass**

- [ ] **Step 6: `/simplify`**

- [ ] **Step 7: Ruff + commit**

```bash
uv run ruff check src/conexus/cli/wiki_migrate.py src/conexus/cli/__main__.py
git add src/conexus/cli/wiki_migrate.py src/conexus/cli/__main__.py src/conexus/tests/cli/test_wiki_migrate.py
git commit -m "feat(cli): add 'conexus wiki migrate' subcommand"
```

---

### Task 11: System prompt update

**Files:**
- Modify: `src/conexus/core/identity/prompt.py`
- Test: `src/conexus/tests/core/identity/test_prompt_wiki_guidance.py` (NEW)

**Spec refs:** §9 (citation format), §7 (tool guidance)

- [ ] **Step 1: Write failing test**

```python
# test_prompt_wiki_guidance.py
from conexus.core.identity.prompt import DEFAULT_MEMORY_PROMPT_PT_BR

def test_prompt_mentions_three_file_pattern():
    p = DEFAULT_MEMORY_PROMPT_PT_BR.lower()
    assert "index.md" in p
    assert "log.md" in p

def test_prompt_mentions_citation_format():
    assert "[" in DEFAULT_MEMORY_PROMPT_PT_BR and "#" in DEFAULT_MEMORY_PROMPT_PT_BR
    assert "wiki_search" in DEFAULT_MEMORY_PROMPT_PT_BR

def test_prompt_mentions_lint_tool():
    assert "wiki_lint" in DEFAULT_MEMORY_PROMPT_PT_BR
```

- [ ] **Step 2: Run test, verify failure**

- [ ] **Step 3: Update `prompt.py`**

Append to existing `DEFAULT_MEMORY_PROMPT_PT_BR` (or replace if it already has memory guidance):

```python
DEFAULT_MEMORY_PROMPT_PT_BR = """\
Você possui memória persistente em três camadas:

1. **Facts** (memory_get/memory_set/memory_list_facts/memory_delete) — pares chave-valor atômicos.
   Use para preferências, IDs, datas, contatos. Curtos.

2. **Blocks** (block_get/block_set/block_list) — blocos de identidade com orçamento de caracteres.
   Use para persona, contexto do usuário, regras estáveis.

3. **Wiki** (wiki_*) — markdown narrativo por agente, versionado em git.
   Estrutura recomendada (padrão Karpathy):
   - `index.md` — catálogo de páginas; atualize via `wiki_index_update(path, summary)` após cada `wiki_write`.
   - `log.md` — registro cronológico; use `wiki_append_log(kind, title, body)`.
   - Páginas individuais em `topic.md` / `pasta/topico.md`.

Regras de escrita:
- Cada página tem frontmatter YAML automático (created, updated, tags, source, reviewed).
- Idioma do conteúdo segue o idioma da conversa (pt-BR por padrão).
- Ao citar uma página, use o formato `[caminho.md#ancora]` — ex: "Vide [arquitetura.md#wiki-layer]."
- Antes de escrever, busque com `wiki_search(query)` para evitar duplicação.
- Periodicamente, rode `wiki_lint()` para detectar órfãos, links quebrados, stubs.

Decida onde gravar:
- Fato curto e estruturado → memory_set.
- Contexto vivo de identidade → block_set.
- Conhecimento narrativo, decisões, notas → wiki_write + wiki_index_update.
"""
```

- [ ] **Step 4: Re-run tests, verify pass**

- [ ] **Step 5: `/simplify` — keep prompt tight, no fluff**

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check src/conexus/core/identity/prompt.py
git add src/conexus/core/identity/prompt.py src/conexus/tests/core/identity/test_prompt_wiki_guidance.py
git commit -m "feat(identity): system prompt teaches three-file wiki pattern + citation format"
```

---

## Final Phase Review

After Wave 6 commits land:

1. **Run full test suite (batched per `docs/dev-workflow/05-quality-gates.md`):**
   ```bash
   uv run pytest src/conexus/tests/core/memory/wiki/ -v
   uv run pytest src/conexus/tests/core/memory/test_sqlite_store_wiki.py -v
   uv run pytest src/conexus/tests/core/identity/ -v
   uv run pytest src/conexus/tests/cli/ -v
   ```
   Target: **30+ new tests green**, all existing 24+ wiki tests still pass.

2. **Dispatch Opus phase reviewer:**
   > "Phase review: wiki tools redesign. Plan: `docs/superpowers/plans/2026-05-09-wiki-tools-redesign.md`. Spec: `docs/superpowers/specs/2026-05-09-wiki-tools-redesign-design.md`. Verify all 11 tasks shipped, all spec sections covered, no scope creep, no premature features (embeddings/reranker/eval must be absent). Verdict: SHIP / SHIP_WITH_NOTES / NO_GO."

3. **Codex final pass:**
   ```
   /codex:rescue --model gpt-5.3-codex --wait
   Final audit of wiki redesign commits since 4417946. Spec: docs/superpowers/specs/2026-05-09-wiki-tools-redesign-design.md.
   Look for: type/signature mismatches across modules, missing imports, unused vars, ruff issues, test gaps, edge cases in mtime reconciliation. Verdict: APPROVE or NO-GO with blockers.
   ```

4. **Live test in Studio:** restart Studio, exercise validator agent's wiki tools end-to-end (write → search → list → lint → index_update → move → delete).

5. **Update `.brain`** via `/nexus-checkpoint` — mark phase complete, log task IDs T-065 through T-075.

---

## Parallel Dispatch Summary

| Wave | Tasks | Parallel? | Files Touched |
|------|-------|-----------|---------------|
| 1 | T1, T2, T3 | **Yes (3-way)** | `frontmatter.py`, `chunking.py`, `citations.py` (disjoint) |
| 2 | T4 | No | `sqlite_store.py` |
| 3 | T5 | No | `index.py`, `index_sqlite.py` |
| 4 | T6, T7 | **Yes (2-way)** | `wiki_store.py` + `__init__.py` (T6); `lint.py` (T7) |
| 5 | T8, T9 | **Yes (2-way)** | `identity/tools.py` (T8); `cli/identity_runtime.py` (T9) |
| 6 | T10, T11 | **Yes (2-way)** | `cli/wiki_migrate.py` + `__main__.py` (T10); `identity/prompt.py` (T11) |

**Total: 11 tasks across 6 waves. Theoretical minimum wall-clock = 6 codex round-trips (assuming each wave's slowest task dominates).**
