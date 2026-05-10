# Wiki Tools Redesign — Design Spec

> **Status:** approved 2026-05-09. Implements doc §closing opinion steps 1 + maintenance discipline (§12) + citations (§13) from `docs/wiki/agents-framework/07-rag-and-wiki.md`. Adopts Karpathy's three-file pattern (index.md / log.md / pages) + ingest/query/lint operations.
>
> **Non-goals:** embeddings, sqlite-vec, reranker, eval harness, backlink graph, auto-dedup. All deferred per "best solution but not overengineered" principle.

---

## 1. Goal

Upgrade the Conexus wiki layer from "filename + grep" to a professional, durable knowledge surface:

1. **Retrieval** that returns ranked sections with citation metadata (FTS5 BM25 over markdown-aware chunks).
2. **Discipline** the agent follows by default: frontmatter every page, `index.md` maintained on writes, `log.md` standardized, lint on demand.
3. **Tool surface** the agent can navigate confidently (delete/exists/move/lint/index_update fill current gaps).
4. **Future-proof index** that extends to embeddings/rerankers later without redesign.

Single-agent and team-aware. Local-language and pt-BR content both supported via `unicode61 remove_diacritics 2` tokenizer. Backwards-compatible with existing `LocalBackend` and `GitHubAppBackend`.

---

## 2. Architecture

```
WikiStore (facade)
  ├── WikiBackend (existing: LocalBackend | GitHubAppBackend)
  └── WikiIndex (NEW Protocol)
       └── SqliteFtsIndex (NEW impl, lives in conexus.db)
            ├── wiki_pages       — one row per .md file, with frontmatter
            ├── wiki_chunks      — one row per heading section
            └── wiki_chunks_fts  — FTS5 virtual table over chunks.body
```

**Two sources of truth, reconciled honestly.** `.md` files are the source. The SQLite index is a cache. Every read/search compares file `mtime` vs stored `mtime` and reindexes stale paths lazily. `_pull()` (GitHub backend) brings external changes → next query auto-reindexes affected files.

**Composition, not inheritance.** `WikiStore.__init__` takes `(backend, index=None)`. If `index=None`, falls back to legacy substring search (back-compat for tests / on-disk-only usage).

**Where each module lives:**

```
src/conexus/core/memory/wiki/
  backend.py            existing — Protocol + safe_join (unchanged)
  local.py              existing — LocalBackend (unchanged)
  github_app.py         existing — GitHubAppBackend (unchanged)
  git_auth.py           existing — JWT (unchanged)
  index.py              NEW       — WikiIndex Protocol
  index_sqlite.py       NEW       — SqliteFtsIndex impl
  chunking.py           NEW       — markdown_chunks(text, path) -> list[Chunk]
  frontmatter.py        NEW       — parse(text), inject(text, defaults), validate(meta)
  lint.py               NEW       — lint_wiki(backend, index) -> LintReport
  citations.py          NEW       — format/parse/validate
src/conexus/core/memory/wiki_store.py
                        ENHANCED  — composes index, new methods
src/conexus/core/identity/tools.py
                        ENHANCED  — exposes new tools
src/conexus/core/memory/sqlite_store.py
                        ENHANCED  — adds 3 tables + helpers
src/conexus/cli/identity_runtime.py
                        ENHANCED  — wires SqliteFtsIndex into WikiStore
```

---

## 3. Data Model

### 3.1 New SQLite tables (in `conexus.db`)

```sql
-- One row per markdown file, with parsed frontmatter
CREATE TABLE IF NOT EXISTS wiki_pages (
    agent_id     TEXT NOT NULL,
    path         TEXT NOT NULL,           -- relative POSIX path inside wiki root
    mtime_ns     INTEGER NOT NULL,        -- file mtime_ns at time of indexing
    created      TEXT,                    -- frontmatter created (YYYY-MM-DD)
    updated      TEXT,                    -- frontmatter updated (YYYY-MM-DD)
    tags         TEXT,                    -- JSON array
    source       TEXT,                    -- frontmatter source
    reviewed     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (agent_id, path)
);

-- One row per heading section
CREATE TABLE IF NOT EXISTS wiki_chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id      TEXT NOT NULL,
    path          TEXT NOT NULL,
    header_path   TEXT NOT NULL,          -- JSON array, e.g. ["# Notes","## 2026-05-09"]
    line_start    INTEGER NOT NULL,
    line_end      INTEGER NOT NULL,
    body          TEXT NOT NULL,
    FOREIGN KEY (agent_id, path) REFERENCES wiki_pages(agent_id, path) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS wiki_chunks_path ON wiki_chunks(agent_id, path);

-- FTS5 virtual table — content-rowid linked to wiki_chunks
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_chunks_fts USING fts5(
    body,
    content='wiki_chunks',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

-- Triggers keep FTS in sync
CREATE TRIGGER IF NOT EXISTS wiki_chunks_ai AFTER INSERT ON wiki_chunks BEGIN
    INSERT INTO wiki_chunks_fts(rowid, body) VALUES (new.id, new.body);
END;
CREATE TRIGGER IF NOT EXISTS wiki_chunks_ad AFTER DELETE ON wiki_chunks BEGIN
    INSERT INTO wiki_chunks_fts(wiki_chunks_fts, rowid, body) VALUES ('delete', old.id, old.body);
END;
CREATE TRIGGER IF NOT EXISTS wiki_chunks_au AFTER UPDATE ON wiki_chunks BEGIN
    INSERT INTO wiki_chunks_fts(wiki_chunks_fts, rowid, body) VALUES ('delete', old.id, old.body);
    INSERT INTO wiki_chunks_fts(rowid, body) VALUES (new.id, new.body);
END;
```

**Per-agent isolation.** `agent_id` column scopes all rows. Multi-agent deployments don't cross-contaminate.

### 3.2 Frontmatter schema

YAML between `---` fences at top of every `.md`:

```yaml
---
created: 2026-05-09
updated: 2026-05-09
tags: [wiki, design]
source: brainstorm
reviewed: false
---
```

Field rules:
- `created`: ISO date. Auto-injected on write if missing.
- `updated`: ISO date. Auto-set on every `wiki_write`.
- `tags`: list of strings. Optional. Default `[]`.
- `source`: free string (`brainstorm`, `ingest:url`, `manual`, `chat:2026-05-09`). Optional.
- `reviewed`: bool. **Only settable by humans via Studio UI** — never by agent tools (trust gradient, doc §12).

Malformed YAML → `wiki_write` returns hard error. Missing fields → soft warning + auto-fill where possible.

---

## 4. WikiIndex Protocol

```python
@runtime_checkable
class WikiIndex(Protocol):
    """Index over a wiki backend. Reconciles via mtime; honest two-source-of-truth."""

    def reindex_path(self, path: str, content: str, mtime_ns: int) -> None: ...
    def drop_path(self, path: str) -> None: ...
    def reconcile(self, paths: dict[str, int]) -> None:
        """Compare paths {path: mtime_ns} vs stored; reindex stale, drop missing."""
    def search(self, query: str, k: int = 10) -> list[SearchHit]: ...
    def page_meta(self, path: str) -> PageMeta | None: ...
    def all_pages(self) -> list[PageMeta]: ...
```

```python
@dataclass(frozen=True)
class SearchHit:
    path: str
    header_path: list[str]
    snippet: str            # FTS5 snippet() with <mark>...</mark>
    score: float            # negative BM25 (lower = better, normalized to 0..1 ascending)
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
```

### 4.1 SqliteFtsIndex behavior

- **`reindex_path(path, content, mtime_ns)`**: parse frontmatter, upsert `wiki_pages`, delete + reinsert chunks for that path. Triggers handle FTS sync.
- **`reconcile(paths)`**: `paths` is `{path: mtime_ns}` from a backend `list()`. For each, if stored `mtime_ns < new mtime_ns` (or no row): re-read from backend, reindex. For stored paths not in `paths`: drop. Bounded cost by changed-file count.
- **`search(query, k)`**: SQL `SELECT ... FROM wiki_chunks_fts JOIN wiki_chunks ... WHERE wiki_chunks_fts MATCH ? ORDER BY rank LIMIT k`. Returns `SearchHit` with `snippet(wiki_chunks_fts, 0, '<mark>', '</mark>', '...', 32)`.

### 4.2 When reconcile runs

- Before `WikiStore.search()` — single call, full reconcile against backend `list()`.
- After `WikiStore.write()` — single-path reindex.
- After `WikiStore.delete()` — single-path drop.
- After `WikiStore.move()` — drop old, reindex new.
- Not on `read()`/`list()` — those don't query the index.

For GitHubAppBackend: `_pull()` runs inside `read/list/search`, then reconcile catches mtime changes from upstream commits.

---

## 5. Markdown Chunking

```python
def markdown_chunks(text: str, max_tokens: int = 800, overlap_tokens: int = 50) -> list[Chunk]:
    """
    Split markdown by ATX headings (#, ##, ###).
    Each chunk = one heading section, with header_path lineage preserved.
    Sections > max_tokens are recursively split with overlap.
    Frontmatter (--- YAML ---) at top is excluded from chunk bodies.
    """
```

**Output shape** (internal, becomes `wiki_chunks` rows):

```python
@dataclass(frozen=True)
class Chunk:
    header_path: list[str]   # ["# Notes", "## 2026-05-09", "### Section"]
    line_start: int          # 1-based, inclusive
    line_end: int            # 1-based, inclusive
    body: str                # raw markdown (heading line included)
```

Token estimate: simple `len(body) // 4` heuristic. No tokenizer dependency. Good enough for chunk-size cap.

Edge cases:
- File with no headings → single chunk covering the whole body, `header_path=[]`.
- Empty file (after frontmatter) → no chunks (page row exists, no chunks).
- Headings deeper than `###` → treated as content within their parent `###` section.

---

## 6. Frontmatter Module

```python
def parse(text: str) -> tuple[dict, str]:
    """Returns (meta_dict, body_without_frontmatter). Empty meta if none."""

def inject(text: str, defaults: dict) -> str:
    """Adds frontmatter if missing; updates 'updated' field if present.
       Never overwrites 'created'. Never overwrites 'reviewed'."""

def validate(meta: dict) -> list[str]:
    """Returns list of warning strings. Empty = valid. Hard errors raise ValueError."""
```

Hard error: malformed YAML, non-dict frontmatter root, `reviewed` not bool, `created`/`updated` not ISO date.
Soft warning: missing `created`/`updated`/`source`/`tags`. Auto-injected with sensible defaults.

`wiki_write(path, content)` flow:
1. Parse incoming `content`.
2. If frontmatter missing, inject defaults (`created=today`, `updated=today`, `tags=[]`, `reviewed=false`).
3. If frontmatter present, set `updated=today`, leave `created`/`reviewed` alone.
4. Validate. Hard error → return `{ok: false, error: ...}`. Soft warnings → continue with `warnings`.
5. Write to backend.
6. Reindex.

---

## 7. Tool Surface

Exposed on `IdentityTools` (per-agent, registered when `identity.enabled`):

| Tool | Signature | Returns |
|------|-----------|---------|
| `wiki_read` | `(path: str)` | str |
| `wiki_write` | `(path: str, content: str)` | `{ok, path, warnings?}` |
| `wiki_list` | `(folder: str = "")` | list[str] |
| `wiki_search` | `(query: str, k: int = 10)` | `list[{path, header_path, snippet, score, line_start, line_end}]` |
| `wiki_append_log` | `(kind: str, title: str, body: str = "")` | `{ok}` |
| `wiki_delete` | `(path: str)` | `{ok, path}` |
| `wiki_exists` | `(path: str)` | bool |
| `wiki_move` | `(src: str, dst: str)` | `{ok, src, dst, backlinks_updated: int}` |
| `wiki_lint` | `()` | LintReport (see §8) |
| `wiki_index_update` | `(path: str, summary: str)` | `{ok}` — appends/replaces line in `index.md` |

**Backlink updates in `wiki_move`:** scan all `.md` for `](src)`, `[[src]]`, `[[src#`, replace with `dst`. Single regex pass. Returns count.

**Tool descriptions written for LLM clarity in English** (Python docstrings; LLMs follow English instructions best). Behavioral guidance ("write notes in user's language") goes in the system prompt, not docstrings.

---

## 8. Lint

```python
@dataclass(frozen=True)
class LintReport:
    orphans: list[str]              # pages not referenced from index.md and not the index itself
    dead_links: list[tuple[str, str]]  # (page, broken_target)
    missing_frontmatter: list[str]  # pages where frontmatter parse returned empty meta
    stub_pages: list[str]           # pages with body < 200 chars after frontmatter
    stale_index: list[str]          # paths referenced from index.md that don't exist on disk

    @property
    def total_issues(self) -> int: ...
```

`wiki_lint()` runs five checks against backend + index. Read-only — never modifies files. Agent calls it; surfaces issues; agent (or human) fixes.

No scheduling. If becomes painful at scale → add to APScheduler later. Per "not overengineered."

---

## 9. Citations

**Format** (system prompt instructs agent):

```
[path#header_anchor]
```

`header_anchor` is the slugified last header in the chunk's `header_path`. Example:

```
Conexus uses pt-BR for prompts [conventions.md#language].
```

**Validation** (`citations.validate(text, backend) -> list[InvalidCitation]`):
- Parse `[X#Y]` patterns from agent output.
- For each: check `wiki_exists(X)`. If exists, check `Y` matches a known header anchor.
- Return list of invalid; **do not strip from output** (degrade gracefully — visible to user, logged for observability).

Citation enforcement is *advisory* in this spec. Hard validation in `agent_handler` post-processor is deferred.

---

## 10. Migration Path

One-shot CLI: `conexus wiki migrate [--agent NAME]`.

Steps per agent:
1. Walk wiki root via backend `list()`.
2. For each `.md`: read, parse frontmatter. If missing/incomplete, inject defaults using file `mtime` for `created` (best estimate). Soft warnings logged.
3. Build initial FTS index via `SqliteFtsIndex.reconcile(paths)`.
4. Write a migration log entry to `log.md`.

Idempotent — re-running detects already-migrated pages by frontmatter presence.

---

## 11. Backwards Compatibility

- `WikiStore(backend)` with no `index` arg → legacy mode, substring search via `backend.search()`. All existing tests pass unchanged.
- Existing wiki content without frontmatter still readable. `wiki_lint` flags them; agent or migration fills them in.
- `wiki_search` shape changes from `[{path, snippet}]` to `[{path, header_path, snippet, score, line_start, line_end}]`. Old shape is a strict subset → consumers reading only `path`/`snippet` keep working. Tests asserting full equality must update.

---

## 12. Testing Strategy

| Module | Test type | Notes |
|--------|-----------|-------|
| `chunking.py` | unit, pure | sample markdown fixtures; verify header_path, line ranges, oversized splits |
| `frontmatter.py` | unit, pure | parse/inject/validate; YAML edge cases |
| `citations.py` | unit, pure | format + parse round-trip; invalid citation detection |
| `lint.py` | unit + integration | LocalBackend + tmp_path; verify each check |
| `index_sqlite.py` | integration | tmp SQLite; reindex/reconcile/search round-trip; trigger sync |
| `wiki_store.py` | integration | LocalBackend + SqliteFtsIndex; full write→search→delete flow |
| `identity/tools.py` | integration | agent-level smoke test for new tools |
| `cli wiki migrate` | integration | tmp wiki with mixed frontmatter; verify idempotent |

Target: **30+ new tests, all passing on Windows batched runner.** Existing 24+ wiki tests stay green.

---

## 13. Out of Scope (Explicit Deferrals)

| Deferred | Why | Revisit when |
|----------|-----|--------------|
| Embeddings + sqlite-vec | Doc §closing opinion step 4 — premature at current scale | Wiki > 1k notes OR semantic queries needed |
| Reranker (bge-reranker-v2-m3 / Cohere) | Doc §closing opinion step 2 — only after BM25 ceiling visible | After eval harness shows BM25 precision plateau |
| Eval harness (Ragas) | Doc §closing opinion step 3 — needs real eval set | Before 2nd retrieval upgrade |
| Backlink graph + `[[note]]` parsing | YAGNI — Obsidian compatibility not a current requirement | If Obsidian becomes primary human UI |
| Auto-dedup on write | Doc §12 — needs embeddings to do well | After embeddings ship |
| Scheduled lint job | Manual lint sufficient at current scale | If wiki health degrades over months |
| GraphRAG | Doc §5 — wrong tool for personal wiki | If global/aggregative queries become a pattern |
| Async git ops in GitHubAppBackend | Existing tech debt — orthogonal to this spec | When event-loop blocking measurably hurts |

---

## 14. Implementation Order (preview for plan)

1. **Foundation** — `frontmatter.py`, `chunking.py`, `citations.py` (pure modules, fully unit-tested).
2. **Index** — `wiki_pages` + `wiki_chunks` + FTS table in `sqlite_store.py`; `index.py` Protocol; `index_sqlite.py` impl with reconcile.
3. **Store** — `WikiStore` enhancement (compose index, new methods, frontmatter-aware write).
4. **Lint** — `lint.py` module + `wiki_lint` tool.
5. **Tools** — expose `wiki_delete`, `wiki_exists`, `wiki_move`, `wiki_lint`, `wiki_index_update` on `IdentityTools`.
6. **Wiring** — `identity_runtime._build_wiki` constructs `SqliteFtsIndex` and passes into `WikiStore`.
7. **Migration CLI** — `conexus wiki migrate` subcommand.
8. **System prompt update** — `DEFAULT_MEMORY_PROMPT_PT_BR` (and English variant) gain three-file pattern + citation format guidance.

Each step ships green tests + commit. Plan will decompose further into bite-sized subagent tasks.

---

## 15. Success Criteria

- All 10 tools callable from agent; existing 5 backwards-compatible.
- `wiki_search("café")` finds notes containing `cafe` (diacritic insensitive).
- Reconcile after external git pull picks up upstream commits without manual reindex.
- `wiki_lint` reports five categories on a deliberately-broken sample wiki.
- Migration CLI converts an existing wiki to frontmatter-compliant + FTS-indexed in one run.
- 30+ new tests pass; 24+ existing pass.
- Zero new infra (no new services, no new dependencies beyond stdlib + existing deps).
