# Memory & Wiki Architecture — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship local-backend wiki, framework-default memory-routing prompt, and notes-pack tool clarity so identity-enabled agents reliably write the right kind of memory to the right store on first try.

**Architecture:** `WikiBackend` Protocol with `LocalBackend` impl. `WikiStore` becomes facade picking backend from SKILL.md. Identity context auto-prepends pt-BR memory-routing guidance. Notes-pack tool descriptions tightened to disambiguate from facts. Schema for `facts` table unchanged (deferred to Phase 2 with extractor).

**Tech Stack:** Python 3.12, pydantic v2, pytest, SQLite, FastAPI (Studio), litellm.

**Spec:** `docs/superpowers/specs/2026-05-08-memory-and-wiki-architecture-design.md`

---

## Model routing for execution

| Task type | Model |
|---|---|
| Protocol + new files (LocalBackend, prompt template) | sonnet |
| Schema/config changes (skill_loader, identity_runtime) | haiku |
| Refactors of existing consumers (WikiStore facade) | codex (touches multiple call sites) |
| Tool description edits, .gitignore, SKILL.md edits | haiku |
| Phase review (post-task-11) | opus |
| Plan validation (pre-execution) | codex |

## Parallel dispatch groups

These task groups have no inter-dependencies and can dispatch concurrently:

- **Group A (independent foundations):** Tasks 4, 6, 8, 10
- **Group B (consumers, sequential):** Tasks 1 → 2 → 3 → 5 (wiki stack); Tasks 7, 9 after deps
- **Group C (integration, after B):** Task 11

Note: Tasks 1 and 2 must run sequentially because `wiki/__init__.py` re-exports `LocalBackend` (created in Task 2). Task 1 ships only the Protocol; `__init__.py` is empty until Task 2.

## File map

**New files:**
| Path | Responsibility |
|---|---|
| `src/conexus/core/memory/wiki/__init__.py` | Package marker, re-exports |
| `src/conexus/core/memory/wiki/backend.py` | `WikiBackend` Protocol + path-safety mixin |
| `src/conexus/core/memory/wiki/local.py` | `LocalBackend` impl (filesystem) |
| `src/conexus/core/identity/prompt.py` | Default pt-BR memory-routing template |
| `src/conexus/tests/core/memory/wiki/__init__.py` | Test package marker |
| `src/conexus/tests/core/memory/wiki/test_local.py` | LocalBackend behavior + path traversal |
| `src/conexus/tests/core/identity/test_prompt.py` | Prompt assembly with/without override |

**Modified files:**
| Path | Change |
|---|---|
| `src/conexus/core/memory/wiki_store.py` | Becomes facade over `WikiBackend`, drops git logic to `LocalBackend` (no remote sync in Phase 1) |
| `src/conexus/core/identity/context.py` | Prepends prompt template when `identity.enabled` |
| `src/conexus/core/config/skill_loader.py` | `WikiSection.backend` field + `prompt_override` |
| `src/conexus/cli/identity_runtime.py` | Instantiates backend by `cfg.wiki.backend` |
| `packs/notes/tools.py` | Sharper `_tool_schemas` descriptions |
| `agents/validator/SKILL.md` | Adds `identity.wiki.backend: local` |
| `.gitignore` | `agents/*/wiki/` |

---

## Task 1: WikiBackend Protocol

**Model:** sonnet
**Depends on:** none
**Files:**
- Create: `src/conexus/core/memory/wiki/__init__.py`
- Create: `src/conexus/core/memory/wiki/backend.py`
- Create: `src/conexus/tests/core/memory/wiki/__init__.py`
- Create: `src/conexus/tests/core/memory/wiki/test_backend.py`

- [ ] **Step 1: Write failing tests for Protocol + safe_join**

```python
# src/conexus/tests/core/memory/wiki/__init__.py
# (empty)
```

```python
# src/conexus/tests/core/memory/wiki/test_backend.py
"""WikiBackend Protocol contract + safe_join helper."""
from __future__ import annotations

import os
import pytest

from conexus.core.memory.wiki.backend import WikiBackend, safe_join


def test_protocol_runtime_checkable():
    class Stub:
        def read(self, p): return ""
        def write(self, p, c): pass
        def list(self, f=""): return []
        def search(self, q): return []
        def exists(self, p): return False
        def delete(self, p): pass

    assert isinstance(Stub(), WikiBackend)


def test_safe_join_resolves_normal_path(tmp_path):
    p = safe_join(tmp_path, "a/b.md")
    assert p == (tmp_path / "a" / "b.md").resolve()


def test_safe_join_rejects_dotdot(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, "../escape.md")


def test_safe_join_rejects_absolute(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, "/etc/passwd")


def test_safe_join_rejects_backslash(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, "a\\b.md")


def test_safe_join_rejects_empty(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, "")


@pytest.mark.skipif(os.name == "nt", reason="symlinks need admin on Windows")
def test_safe_join_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        safe_join(tmp_path, "link/x.md")
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest src/conexus/tests/core/memory/wiki/test_backend.py -v`
Expected: FAIL — module/symbols missing.

- [ ] **Step 3: Create empty package marker**

```python
# src/conexus/core/memory/wiki/__init__.py
"""Wiki backend package. LocalBackend is added in Task 2."""
from conexus.core.memory.wiki.backend import WikiBackend, safe_join

__all__ = ["WikiBackend", "safe_join"]
```

- [ ] **Step 4: Define Protocol**

```python
# src/conexus/core/memory/wiki/backend.py
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
```

- [ ] **Step 5: Verify tests pass**

Run: `uv run pytest src/conexus/tests/core/memory/wiki/test_backend.py -v`
Expected: 6 passed (5 on Windows, symlink test skipped).

- [ ] **Step 6: Commit**

```bash
git add src/conexus/core/memory/wiki/ src/conexus/tests/core/memory/wiki/
git commit -m "feat(wiki): add WikiBackend protocol and safe_join helper"
```

---

## Task 2: LocalBackend implementation

**Model:** sonnet
**Depends on:** Task 1
**Files:**
- Create: `src/conexus/core/memory/wiki/local.py`
- Modify: `src/conexus/core/memory/wiki/__init__.py` (add `LocalBackend` export)
- Create: `src/conexus/tests/core/memory/wiki/test_local.py`

- [ ] **Step 1: Write failing tests**

```python
# src/conexus/tests/core/memory/wiki/test_local.py
"""LocalBackend: filesystem wiki ops + path safety."""
from __future__ import annotations

import pytest

from conexus.core.memory.wiki import LocalBackend


def test_write_then_read_roundtrip(tmp_path):
    b = LocalBackend(tmp_path)
    b.write("note.md", "hello")
    assert b.read("note.md") == "hello"


def test_list_returns_relative_posix_paths(tmp_path):
    b = LocalBackend(tmp_path)
    b.write("a.md", "x")
    b.write("sub/b.md", "y")
    assert sorted(b.list()) == ["a.md", "sub/b.md"]


def test_list_folder_filters(tmp_path):
    b = LocalBackend(tmp_path)
    b.write("a.md", "x")
    b.write("sub/b.md", "y")
    assert b.list("sub") == ["sub/b.md"]


def test_search_returns_snippets(tmp_path):
    b = LocalBackend(tmp_path)
    b.write("note.md", "the quick brown fox jumps over the lazy dog")
    hits = b.search("brown")
    assert len(hits) == 1
    assert hits[0]["path"] == "note.md"
    assert "brown" in hits[0]["snippet"]


def test_exists_and_delete(tmp_path):
    b = LocalBackend(tmp_path)
    b.write("x.md", "v")
    assert b.exists("x.md")
    b.delete("x.md")
    assert not b.exists("x.md")


def test_read_missing_raises(tmp_path):
    b = LocalBackend(tmp_path)
    with pytest.raises(FileNotFoundError):
        b.read("ghost.md")


def test_path_traversal_rejected(tmp_path):
    b = LocalBackend(tmp_path)
    with pytest.raises(ValueError):
        b.write("../escape.md", "x")
    with pytest.raises(ValueError):
        b.read("../../../etc/passwd")


def test_absolute_path_rejected(tmp_path):
    b = LocalBackend(tmp_path)
    with pytest.raises(ValueError):
        b.write("/abs/path.md", "x")


def test_root_auto_created(tmp_path):
    target = tmp_path / "deep" / "nested" / "wiki"
    b = LocalBackend(target)
    b.write("a.md", "x")
    assert (target / "a.md").is_file()
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest src/conexus/tests/core/memory/wiki/test_local.py -v`
Expected: FAIL — `LocalBackend` not defined.

- [ ] **Step 3: Implement LocalBackend**

```python
# src/conexus/core/memory/wiki/local.py
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
```

- [ ] **Step 4: Re-export LocalBackend in package**

```python
# src/conexus/core/memory/wiki/__init__.py — replace
"""Wiki backend package."""
from conexus.core.memory.wiki.backend import WikiBackend, safe_join
from conexus.core.memory.wiki.local import LocalBackend

__all__ = ["WikiBackend", "LocalBackend", "safe_join"]
```

- [ ] **Step 5: Verify tests pass**

Run: `uv run pytest src/conexus/tests/core/memory/wiki/test_local.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add src/conexus/core/memory/wiki/ src/conexus/tests/core/memory/wiki/test_local.py
git commit -m "feat(wiki): add LocalBackend filesystem implementation"
```

---

## Task 3: WikiStore facade refactor

**Model:** codex (touches existing consumers, requires care)
**Depends on:** Task 2
**Files:**
- Modify: `src/conexus/core/memory/wiki_store.py`
- Modify: `src/conexus/tests/test_framework_wiki_store.py` (drop `autocommit=False`)
- Modify: `src/conexus/tests/core/identity/test_context_assembly.py` (constructor)
- Modify: `src/conexus/tests/core/identity/test_identity_tools.py` (constructor)

This task replaces `WikiStore`'s direct filesystem + git logic with a thin facade over `WikiBackend`. Phase 1 only wires `LocalBackend`. Git logic is dropped (Phase 2 `GitHubAppBackend` owns remote sync internally). `autocommit` and `ssh_cmd` params are removed — no consumer needs them in Phase 1. **Identity runtime wiring is owned by Task 5.**

- [ ] **Step 1: Write failing test asserting new API**

```python
# Append to src/conexus/tests/test_framework_wiki_store.py
def test_wikistore_accepts_path_via_local_classmethod(tmp_path):
    from conexus.core.memory.wiki_store import WikiStore
    store = WikiStore.local(tmp_path)
    store.write("a.md", "x")
    assert store.read("a.md") == "x"


def test_wikistore_accepts_backend_directly(tmp_path):
    from conexus.core.memory.wiki import LocalBackend
    from conexus.core.memory.wiki_store import WikiStore
    store = WikiStore(LocalBackend(tmp_path))
    store.write("a.md", "y")
    assert store.list() == ["a.md"]


def test_wikistore_legacy_path_constructor_still_works(tmp_path):
    """Back-compat: passing a path builds LocalBackend internally."""
    from conexus.core.memory.wiki_store import WikiStore
    store = WikiStore(str(tmp_path))
    store.write("a.md", "z")
    assert store.read("a.md") == "z"
```

- [ ] **Step 2: Verify test fails**

Run: `uv run pytest src/conexus/tests/test_framework_wiki_store.py -k "wikistore_" -v`
Expected: FAIL — `WikiStore.local` missing OR positional-arg mismatch.

- [ ] **Step 3: Rewrite `wiki_store.py` as facade**

```python
# src/conexus/core/memory/wiki_store.py
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
```

- [ ] **Step 4: Update existing test call sites**

Replace `WikiStore(tmp_wiki_dir, autocommit=False)` → `WikiStore.local(tmp_wiki_dir)` in:
- `src/conexus/tests/test_framework_wiki_store.py` (6 sites, lines 9/15/32/43/51/65)
- `src/conexus/tests/core/identity/test_context_assembly.py` line 23: `WikiStore(str(tmp_path / "wiki"))` → `WikiStore.local(tmp_path / "wiki")`
- `src/conexus/tests/core/identity/test_identity_tools.py` line 18: same replacement

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest src/conexus/tests -x -q`
Expected: all previously-passing tests still pass. `identity_runtime.py` still uses old `WikiStore(str(...))` — that line is intentionally untouched here; Task 5 owns it. Run `uv run pytest src/conexus/tests -k "wiki_store or identity_tools or context_assembly" -v` to scope verification.

- [ ] **Step 6: Commit**

```bash
git add src/conexus/core/memory/wiki_store.py src/conexus/tests/test_framework_wiki_store.py src/conexus/tests/core/identity/test_context_assembly.py src/conexus/tests/core/identity/test_identity_tools.py
git commit -m "refactor(wiki): make WikiStore a facade over WikiBackend"
```

---

## Task 4: SKILL.md schema — backend + prompt_override

**Model:** haiku
**Depends on:** none
**Files:**
- Modify: `src/conexus/core/config/skill_loader.py`
- Test: `src/conexus/tests/test_framework_skill_loader.py`

- [ ] **Step 1: Write failing test**

```python
# Append to src/conexus/tests/test_framework_skill_loader.py
def test_wiki_section_accepts_backend_field():
    from conexus.core.config.skill_loader import WikiSection
    s = WikiSection(backend="local", dir="./wiki")
    assert s.backend == "local"
    assert s.dir == "./wiki"


def test_wiki_section_defaults_backend_to_local():
    from conexus.core.config.skill_loader import WikiSection
    s = WikiSection(dir="./wiki")
    assert s.backend == "local"


def test_wiki_section_rejects_unknown_backend():
    import pytest
    from conexus.core.config.skill_loader import WikiSection
    with pytest.raises(ValueError):
        WikiSection(backend="ftp", dir="./wiki")


def test_identity_section_accepts_prompt_override():
    from conexus.core.config.skill_loader import IdentitySection
    s = IdentitySection(enabled=True, prompt_override="./custom.md")
    assert s.prompt_override == "./custom.md"


def test_identity_section_default_wiki_is_local():
    """Backward compat: agents without identity.wiki block still get local wiki."""
    from conexus.core.config.skill_loader import IdentitySection
    s = IdentitySection(enabled=True)
    assert s.wiki is not None
    assert s.wiki.backend == "local"
    assert s.wiki.dir == "./wiki"


def test_anna_skill_parses_with_default_wiki():
    """Anna's SKILL.md has identity.enabled but no wiki block — must still load."""
    from pathlib import Path
    from conexus.core.config.skill_loader import parse_skill_file
    p = Path("agents/anna/SKILL.md")
    if not p.exists():
        import pytest
        pytest.skip("anna SKILL.md not present")
    doc = parse_skill_file(str(p))
    assert doc.frontmatter.identity is not None
    assert doc.frontmatter.identity.enabled is True
    assert doc.frontmatter.identity.wiki is not None
    assert doc.frontmatter.identity.wiki.backend == "local"
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest src/conexus/tests/test_framework_skill_loader.py -k "backend or prompt_override" -v`
Expected: FAIL — fields don't exist.

- [ ] **Step 3: Update schema**

```python
# src/conexus/core/config/skill_loader.py — replace WikiSection and IdentitySection
class WikiSection(BaseModel):
    backend: str = "local"
    dir: str = "./wiki"
    inject_index: bool = True
    repo: str | None = None  # Phase 2 (github_app)

    @field_validator("backend")
    @classmethod
    def _validate_backend(cls, v: str) -> str:
        if v not in {"local", "github_app"}:
            raise ValueError(f"unknown wiki backend: {v!r}")
        return v


class IdentitySection(BaseModel):
    enabled: bool = False
    blocks: dict[str, BlockSpec] = Field(default_factory=dict)
    facts: FactsSection = Field(default_factory=FactsSection)
    # Default to local wiki so existing agents (e.g. anna) keep working without
    # adding an explicit `identity.wiki` block. Set to None only via explicit
    # YAML `wiki: null`.
    wiki: WikiSection | None = Field(default_factory=WikiSection)
    history: HistorySection = Field(default_factory=HistorySection)
    prompt_override: str | None = None

    @field_validator("blocks", mode="before")
    @classmethod
    def _coerce_blocks(cls, v):
        if isinstance(v, dict):
            return {k: BlockSpec.coerce(val) for k, val in v.items()}
        return v
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest src/conexus/tests/test_framework_skill_loader.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/conexus/core/config/skill_loader.py src/conexus/tests/test_framework_skill_loader.py
git commit -m "feat(config): add wiki.backend and identity.prompt_override fields"
```

---

## Task 5: IdentityRuntime backend instantiation

**Model:** haiku
**Depends on:** Tasks 2, 4
**Files:**
- Modify: `src/conexus/cli/identity_runtime.py` (dispatch + store `skill_dir`)
- Create: `src/conexus/tests/cli/test_identity_runtime_backends.py`

- [ ] **Step 1: Write failing test**

```python
# src/conexus/tests/cli/test_identity_runtime_backends.py
"""IdentityRuntime dispatches wiki construction by backend field."""
from __future__ import annotations

from pathlib import Path

import pytest

from conexus.core.config.skill_loader import IdentitySection, WikiSection
from conexus.core.memory.sqlite_store import SqliteStore


def _store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(str(tmp_path / "db.sqlite"))


def test_local_backend_creates_wikistore(tmp_path):
    from conexus.cli.identity_runtime import build_identity_runtime
    cfg = IdentitySection(enabled=True, wiki=WikiSection(backend="local", dir="./wiki"))
    rt = build_identity_runtime("a", cfg, _store(tmp_path), tmp_path)
    assert rt is not None
    assert rt.wiki is not None
    rt.wiki.write("x.md", "hi")
    assert (tmp_path / "wiki" / "x.md").read_text(encoding="utf-8") == "hi"


def test_github_app_backend_raises_not_implemented(tmp_path):
    from conexus.cli.identity_runtime import build_identity_runtime
    cfg = IdentitySection(enabled=True, wiki=WikiSection(backend="github_app", dir="./wiki"))
    with pytest.raises(NotImplementedError):
        build_identity_runtime("a", cfg, _store(tmp_path), tmp_path)


def test_no_wiki_block_yields_no_wiki(tmp_path):
    """Explicit `wiki: null` in YAML disables wiki entirely."""
    from conexus.cli.identity_runtime import build_identity_runtime
    cfg = IdentitySection(enabled=True, wiki=None)
    rt = build_identity_runtime("a", cfg, _store(tmp_path), tmp_path)
    assert rt is not None
    assert rt.wiki is None
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest src/conexus/tests/cli/test_identity_runtime_backends.py -v`
Expected: FAIL — `_build_wiki` missing or `github_app` not handled.

- [ ] **Step 3: Update runtime to dispatch on backend**

```python
# src/conexus/cli/identity_runtime.py — replace wiki construction in __init__

# OLD:
#     if cfg.wiki:
#         wiki_path = (skill_dir / cfg.wiki.dir if not Path(cfg.wiki.dir).is_absolute()
#                      else Path(cfg.wiki.dir))
#         wiki_path.mkdir(parents=True, exist_ok=True)
#         self.wiki = WikiStore(str(wiki_path))

# NEW:
        self.skill_dir = skill_dir
        self.wiki: WikiStore | None = None
        if cfg.wiki:
            self.wiki = _build_wiki(cfg.wiki, skill_dir)
```

Note: `skill_dir` becomes a public attribute so callers (`agent_handler.py`, Task 7) can pass it to `assemble_identity_context` without re-touching this file.

Add module-level helper:

```python
# src/conexus/cli/identity_runtime.py — append
def _build_wiki(wiki_cfg, skill_dir: Path) -> WikiStore:
    if wiki_cfg.backend == "local":
        wiki_path = (
            skill_dir / wiki_cfg.dir
            if not Path(wiki_cfg.dir).is_absolute()
            else Path(wiki_cfg.dir)
        )
        return WikiStore.local(wiki_path)
    if wiki_cfg.backend == "github_app":
        raise NotImplementedError(
            "github_app backend lands in Phase 2 — use 'local' for now"
        )
    raise ValueError(f"unknown wiki backend: {wiki_cfg.backend!r}")
```

- [ ] **Step 4: Run identity-runtime tests**

Run: `uv run pytest src/conexus/tests -k "identity_runtime or identity_baseline" -v`
Expected: all pass (3 new + existing).

- [ ] **Step 5: Commit**

```bash
git add src/conexus/cli/identity_runtime.py src/conexus/tests/cli/test_identity_runtime_backends.py
git commit -m "feat(identity): dispatch wiki backend by SKILL.md config"
```

---

## Task 6: Identity prompt template

**Model:** haiku
**Depends on:** none
**Files:**
- Create: `src/conexus/core/identity/prompt.py`
- Create: `src/conexus/tests/core/identity/test_prompt.py`

- [ ] **Step 1: Write failing test**

```python
# src/conexus/tests/core/identity/test_prompt.py
"""Identity prompt template assembly."""
from __future__ import annotations

from conexus.core.identity.prompt import (
    DEFAULT_MEMORY_PROMPT_PT_BR,
    load_memory_prompt,
)


def test_default_prompt_has_three_layers():
    p = DEFAULT_MEMORY_PROMPT_PT_BR
    assert "memory_set" in p
    assert "wiki_write" in p
    assert "notes" in p.lower()
    assert p.startswith("## Memória")


def test_load_returns_default_when_no_override():
    assert load_memory_prompt(None, None) == DEFAULT_MEMORY_PROMPT_PT_BR


def test_load_reads_override_file(tmp_path):
    f = tmp_path / "custom.md"
    f.write_text("custom guidance", encoding="utf-8")
    assert load_memory_prompt(str(f), tmp_path) == "custom guidance"


def test_load_resolves_relative_to_skill_dir(tmp_path):
    (tmp_path / "p.md").write_text("X", encoding="utf-8")
    assert load_memory_prompt("./p.md", tmp_path) == "X"
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest src/conexus/tests/core/identity/test_prompt.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement prompt module**

```python
# src/conexus/core/identity/prompt.py
"""Default memory-routing prompt (pt-BR) + override loader.

Auto-prepended to identity context when `identity.enabled`. Override via
SKILL.md `identity.prompt_override: ./custom.md`.
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_MEMORY_PROMPT_PT_BR = """\
## Memória

Você tem três sistemas de memória:

1. **Fatos** (`memory_set`) — informações atômicas e permanentes sobre o usuário:
   nome, família, preferências, datas importantes, idioma. Use chave em snake_case.
   Exemplos: nome="Leandro", mae="Maria", filha="Ana", cor_favorita="azul".

2. **Wiki** (`wiki_write`) — conteúdo narrativo, projetos, resumos, logs de pesquisa.
   Use quando a informação tem mais de uma frase ou precisa de estrutura.

3. **Notas** (pacote `notes`) — listas efêmeras, lembretes curtos, rascunhos.
   Use só quando o usuário pedir explicitamente "anote" ou "faça uma lista".

Regra: se o usuário compartilha algo sobre quem ele é ou quem está na vida dele,
SEMPRE use `memory_set`. Notas são para tarefas, não para identidade."""


def load_memory_prompt(override: str | None, skill_dir: Path | None) -> str:
    """Return override content if set, else default. Resolves override relative to skill_dir."""
    if not override:
        return DEFAULT_MEMORY_PROMPT_PT_BR
    p = Path(override)
    if not p.is_absolute() and skill_dir is not None:
        p = skill_dir / p
    return p.read_text(encoding="utf-8")
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest src/conexus/tests/core/identity/test_prompt.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/conexus/core/identity/prompt.py src/conexus/tests/core/identity/test_prompt.py
git commit -m "feat(identity): add default pt-BR memory-routing prompt template"
```

---

## Task 7: Context prepends prompt template

**Model:** haiku
**Depends on:** Task 6
**Files:**
- Modify: `src/conexus/core/identity/context.py`
- Modify: `src/conexus/core/agent_handler.py` (pass `runtime.skill_dir` into context call)
- Modify: `src/conexus/tests/core/identity/test_context_assembly.py` (assert prompt prepended)

- [ ] **Step 1: Write failing test**

Append to `src/conexus/tests/core/identity/test_context_assembly.py`:

```python
def test_context_prepends_default_prompt(tmp_path):
    from conexus.core.config.skill_loader import IdentitySection
    from conexus.core.identity.blocks import BlockStore
    from conexus.core.identity.context import assemble_identity_context
    from conexus.core.identity.prompt import DEFAULT_MEMORY_PROMPT_PT_BR
    from conexus.core.memory.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "db.sqlite"))
    cfg = IdentitySection(enabled=True)
    out = assemble_identity_context("a", cfg, store, None, BlockStore(store), tmp_path)
    assert out.startswith(DEFAULT_MEMORY_PROMPT_PT_BR)


def test_context_uses_prompt_override(tmp_path):
    from conexus.core.config.skill_loader import IdentitySection
    from conexus.core.identity.blocks import BlockStore
    from conexus.core.identity.context import assemble_identity_context
    from conexus.core.memory.sqlite_store import SqliteStore

    (tmp_path / "custom.md").write_text("CUSTOM-PROMPT", encoding="utf-8")
    store = SqliteStore(str(tmp_path / "db.sqlite"))
    cfg = IdentitySection(enabled=True, prompt_override="./custom.md")
    out = assemble_identity_context("a", cfg, store, None, BlockStore(store), tmp_path)
    assert out.startswith("CUSTOM-PROMPT")


def test_context_disabled_returns_empty(tmp_path):
    from conexus.core.config.skill_loader import IdentitySection
    from conexus.core.identity.blocks import BlockStore
    from conexus.core.identity.context import assemble_identity_context
    from conexus.core.memory.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "db.sqlite"))
    out = assemble_identity_context("a", IdentitySection(enabled=False), store, None, BlockStore(store), tmp_path)
    assert out == ""
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest src/conexus/tests/core/identity/test_context_assembly.py -k "prepends or override or disabled" -v`
Expected: FAIL — prompt not prepended yet.

- [ ] **Step 3: Update `assemble_identity_context` signature + logic**

```python
# src/conexus/core/identity/context.py — full replace
"""Assemble identity context block to prepend to system prompt."""
from __future__ import annotations

from pathlib import Path

from conexus.core.config.skill_loader import IdentitySection
from conexus.core.identity.blocks import BlockStore
from conexus.core.identity.prompt import load_memory_prompt
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


def assemble_identity_context(
    agent_id: str,
    cfg: IdentitySection,
    store: SqliteStore,
    wiki: WikiStore | None,
    blocks: BlockStore,
    skill_dir: Path | None = None,
) -> str:
    if not cfg.enabled:
        return ""

    sections: list[str] = [load_memory_prompt(cfg.prompt_override, skill_dir)]

    for name in cfg.blocks:
        content = blocks.get(agent_id, name)
        if content:
            sections.append(f"## Block: {name}\n{content}")

    if cfg.facts.enabled and cfg.facts.inject_recent > 0:
        recent = store.facts_recent(agent_id, limit=cfg.facts.inject_recent)
        if recent:
            lines = [f"- {f['key']}: {f['value']}" for f in recent]
            sections.append("## Fatos recentes\n" + "\n".join(lines))

    if cfg.wiki and cfg.wiki.inject_index and wiki is not None:
        files = wiki.list("")
        if files:
            lines = [f"- {p}" for p in files]
            sections.append("## Wiki (índice)\n" + "\n".join(lines))

    return "\n\n".join(sections)
```

- [ ] **Step 4: Update `agent_handler.py` to pass `skill_dir`**

In `src/conexus/core/agent_handler.py` lines 116-122, the local variable holding the `IdentityRuntime` is `ir`. Patch the call:

```python
# OLD:
#     identity_ctx = assemble_identity_context(
#         ir.agent_id, ir.cfg, ir.store, ir.wiki, ir.blocks,
#     )
# NEW:
        identity_ctx = assemble_identity_context(
            ir.agent_id, ir.cfg, ir.store, ir.wiki, ir.blocks, ir.skill_dir,
        )
```

`identity_runtime.py` is intentionally NOT modified in this task — `skill_dir` is already stored on the runtime by Task 5. Existing test callers (`test_context_assembly.py`, `test_identity_baseline_e2e.py`) continue to work unchanged because `skill_dir` defaults to `None`.

- [ ] **Step 5: Run identity tests**

Run: `uv run pytest src/conexus/tests -k "identity_baseline or identity_inspector or identity_tools or context_assembly" -v`
Expected: all pass. Default `skill_dir=None` keeps unmodified callers working.

- [ ] **Step 6: Commit**

```bash
git add src/conexus/core/identity/context.py src/conexus/core/agent_handler.py src/conexus/tests/core/identity/test_context_assembly.py
git commit -m "feat(identity): prepend memory-routing prompt to identity context"
```

---

## Task 8: Notes-pack tool description clarity

**Model:** haiku
**Depends on:** none
**Files:**
- Modify: `packs/notes/tools.py`
- Create: `src/conexus/tests/packs/test_notes_descriptions.py`

- [ ] **Step 1: Write failing test**

```python
# src/conexus/tests/packs/test_notes_descriptions.py
"""Notes pack tool descriptions must disambiguate from facts/wiki."""
from __future__ import annotations


def test_add_note_warns_against_personal_info():
    from packs.notes.tools import NotesTools
    desc = NotesTools._tool_schemas["add_note"]["description"]
    assert "memory_set" in desc
    assert "wiki_write" in desc
    assert "efêmera" in desc.lower() or "ephemeral" in desc.lower()


def test_list_notes_description_present():
    from packs.notes.tools import NotesTools
    assert NotesTools._tool_schemas["list_notes"]["description"]


def test_search_notes_description_present():
    from packs.notes.tools import NotesTools
    assert NotesTools._tool_schemas["search_notes"]["description"]
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest src/conexus/tests/packs/test_notes_descriptions.py -v`
Expected: FAIL — current description doesn't mention `memory_set`/`wiki_write`.

- [ ] **Step 3: Tighten descriptions**

```python
# packs/notes/tools.py — replace _tool_schemas only
    _tool_schemas: ClassVar[dict] = {
        "add_note": {
            "description": (
                "Adiciona uma anotação efêmera (lista, recado curto, rascunho). "
                "NÃO use para informações pessoais permanentes (nome, família, "
                "preferências) — para isso use memory_set. NÃO use para conteúdo "
                "narrativo longo — use wiki_write."
            )
        },
        "list_notes": {
            "description": "Lista anotações efêmeras recentes (mais novas primeiro)."
        },
        "search_notes": {
            "description": "Busca por substring nas anotações efêmeras salvas."
        },
    }
```

- [ ] **Step 4: Run pack tests**

Run: `uv run pytest src/conexus/tests -k "notes" -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packs/notes/tools.py src/conexus/tests/packs/test_notes_descriptions.py
git commit -m "feat(notes-pack): sharpen tool descriptions to disambiguate from facts/wiki"
```

---

## Task 9: Validator SKILL.md enables local wiki

**Model:** haiku
**Depends on:** Task 4
**Files:**
- Modify: `agents/validator/SKILL.md`

- [ ] **Step 1: Add wiki section**

Edit `agents/validator/SKILL.md` frontmatter, replace the `identity:` block:

```yaml
identity:
  enabled: true
  blocks:
    user:
      budget_chars: 400
    persona:
      budget_chars: 600
  facts:
    enabled: true
    inject_recent: 5
  wiki:
    backend: local
    dir: ./wiki
    inject_index: true
  history:
    budget_tokens: 3000
    keep_verbatim: 6
    summary_budget: 600
    trigger_pct: 0.8
```

- [ ] **Step 2: Verify SKILL.md parses**

Run: `uv run python -c "from conexus.core.config.skill_loader import parse_skill_file; d = parse_skill_file('agents/validator/SKILL.md'); print(d.frontmatter.identity.wiki)"`
Expected: prints `WikiSection(backend='local', dir='./wiki', inject_index=True, repo=None)`.

- [ ] **Step 3: Commit**

```bash
git add agents/validator/SKILL.md
git commit -m "feat(validator): enable local-backend wiki for e2e testing"
```

---

## Task 10: .gitignore wiki dirs

**Model:** haiku
**Depends on:** none
**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append rule**

Add to `.gitignore`:

```
# Per-agent wiki content (LocalBackend)
agents/*/wiki/
```

- [ ] **Step 2: Verify**

Run: `git check-ignore -v agents/validator/wiki/test.md`
Expected: prints the rule that matches.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore per-agent local wiki content"
```

---

## Task 11: E2E validation in Studio REPL

**Model:** opus (phase review)
**Depends on:** Tasks 1-10
**Files:**
- None (manual verification)

- [ ] **Step 1: Restart Studio**

Run: `uv run conexus studio` (kill any prior instance first via `Stop-Process -Id <pid> -Force`).

- [ ] **Step 2: Open validator REPL, send three identity-shaped messages**

Send each, observe response, then verify DB state.

Message A: `lembre que meu nome é Leandro`
Expected response: tool call to `memory_set(key="nome", value="Leandro")`. Confirmation in pt-BR.

Message B: `escreve uma página de wiki sobre o projeto Conexus`
Expected response: tool call to `wiki_write(path="conexus.md", content=...)`. Confirmation.

Message C: `anota: comprar pão amanhã`
Expected response: tool call to `add_note(text="comprar pão amanhã")`. Confirmation.

- [ ] **Step 3: Verify DB state**

```bash
uv run python -c "
import sqlite3
db = sqlite3.connect('data/conexus.db')
db.row_factory = sqlite3.Row
cur = db.cursor()
print('=== facts[validator] ==='); [print(dict(r)) for r in cur.execute(\"SELECT * FROM facts WHERE agent_id='validator'\").fetchall()]
print('=== notes[validator] ==='); [print(dict(r)) for r in cur.execute(\"SELECT * FROM pack_notes_entries WHERE agent_name='validator' ORDER BY id DESC LIMIT 3\").fetchall()]
import os; print('=== wiki dir ==='); [print(p) for p in os.listdir('agents/validator/wiki')] if os.path.isdir('agents/validator/wiki') else print('(missing)')
"
```

Expected:
- `facts[validator]` contains row `{key: 'nome', value: 'Leandro', ...}`
- `pack_notes_entries` contains "comprar pão amanhã" — and NOT "meu nome é Leandro"
- `agents/validator/wiki/` contains `conexus.md`

- [ ] **Step 4: Cross-session recall**

Reset validator chat (new session). Send: `qual é meu nome?`
Expected: agent answers "Leandro" — pulled from `Fatos recentes` injection.

- [ ] **Step 5: Commit verification artifacts (if any)**

If verification produced log files or screenshots, save under `docs/validation/2026-05-08-memory-phase1/`.

```bash
git add docs/validation/2026-05-08-memory-phase1/ 2>/dev/null || true
git commit -m "docs: validation artifacts for memory phase 1" --allow-empty
```

---

## Task 12: Plan validation via codex (pre-execution)

**Model:** codex (codex:rescue subagent, sonnet baseline)
**Depends on:** plan complete
**Files:** none

This task runs BEFORE Task 1 begins. Output gates execution.

- [ ] **Step 1: Dispatch codex**

Invoke `/codex:rescue` with prompt:

> Validate the implementation plan at `docs/superpowers/plans/2026-05-08-memory-and-wiki-phase1.md` against the spec at `docs/superpowers/specs/2026-05-08-memory-and-wiki-architecture-design.md`. Identify: (1) any spec requirement not covered by a task, (2) any task whose code would not compile or pass its own test, (3) any inter-task type/signature mismatch, (4) any task that touches a file not declared in its `Files:` section, (5) any test that would not actually fail before implementation. Reply with a numbered punch list of issues and a final verdict: APPROVE or REVISE.

- [ ] **Step 2: Apply fixes**

If REVISE, resolve each issue inline in the plan, then re-dispatch codex once. If second pass is REVISE, escalate to user.

If APPROVE, proceed to Task 1.

---

## Task 13: Wiki-keeper subagent post-phase pass

**Model:** existing `wiki-keeper` subagent definition
**Depends on:** Task 11 complete
**Files:** wiki updates only

- [ ] **Step 1: Invoke wiki-keeper**

Use `Agent` tool with `subagent_type: "wiki-keeper"` and prompt:

> Phase 1 of the memory-and-wiki architecture is complete. Spec: `docs/superpowers/specs/2026-05-08-memory-and-wiki-architecture-design.md`. Plan: `docs/superpowers/plans/2026-05-08-memory-and-wiki-phase1.md`. Update `docs/wiki/agents-framework/*.md` to reflect: (a) `WikiBackend` Protocol + `LocalBackend`, (b) `WikiStore` is now a facade, (c) SKILL.md gained `identity.wiki.backend` and `identity.prompt_override` fields, (d) memory-routing prompt is auto-prepended for identity-enabled agents, (e) per-agent local wiki at `agents/<name>/wiki/`. Cite file paths and line numbers from the new code. Do not invent behavior not in the diff.

- [ ] **Step 2: Review wiki diff**

Run: `git diff docs/wiki/agents-framework/`
Confirm citations point to real lines. Fix any drift.

- [ ] **Step 3: Commit wiki updates**

```bash
git add docs/wiki/agents-framework/
git commit -m "docs(wiki): reflect memory-and-wiki Phase 1 architecture"
```

---

## Self-Review

**Spec coverage:**
- Decision 1 (framework prompt) → Tasks 6, 7
- Decision 2 (notes-pack tool clarity) → Task 8
- Decision 3 (schema unchanged) → no task needed (intentional non-change documented in plan header)
- Decision 4 (pluggable backend) → Tasks 1, 2, 3, 5
- Decision 5 (per-agent repo) → Phase 2 only — not in this plan, correctly scoped
- Decision 6 (GitHub App) → Phase 2 only — not in this plan, correctly scoped
- Decision 7 (SKILL.md schema) → Task 4
- File map (new + modified) → all listed files have a task
- Phase 1 task list (12 items in spec) → covered by Tasks 1-11; Task 12 (codex validation) and Task 13 (wiki-keeper) are framework-quality additions per user instruction
- Testing strategy (unit + integration + E2E) → unit (Tasks 2, 4, 6), integration (Task 11), path-traversal unit (Task 2)

**Placeholder scan:** None. All steps have concrete code blocks or shell commands. No "TBD", no "appropriate handling", no "similar to Task N".

**Type consistency:**
- `WikiBackend` Protocol methods (`read`, `write`, `list`, `search`, `exists`, `delete`) match `LocalBackend` impl signatures (Task 2) and `WikiStore` facade delegation (Task 3).
- `WikiStore.__init__` accepts `WikiBackend | str | Path` (Task 3 back-compat shim) — keeps `identity_runtime.py` working between Tasks 3 and 5.
- `WikiSection` field names (`backend`, `dir`, `inject_index`, `repo`) consistent across Tasks 4, 5, 9.
- `IdentitySection.wiki` defaults to `WikiSection()` (local) — Anna's SKILL.md keeps working without `wiki:` block.
- `assemble_identity_context` signature gains `skill_dir: Path | None = None` (Task 7); `IdentityRuntime` is the only mutating caller (Task 5 owns the wiring).
- `load_memory_prompt(override, skill_dir)` (Task 6) called once from `assemble_identity_context` (Task 7) — matches.

**Codex blocker fixes applied (round 1):**
1. ✅ Default local wiki — `Field(default_factory=WikiSection)` + Anna parse test (Task 4).
2. ✅ Task 1/2 import order — `__init__.py` exports only `WikiBackend`/`safe_join` until Task 2 step 4 adds `LocalBackend`.
3. ✅ Failing tests added to Tasks 1, 3, 5, 7, 8.
4. ✅ `identity_runtime.py` edits live only in Task 5 (Task 3 keeps back-compat shim so runtime works in transit).
5. ✅ Symlink + backslash + empty-path safe_join cases (Task 1 step 1).
6. ✅ Existing `WikiStore(...)` call sites (test files + runtime) handled — back-compat shim + explicit test-file rewrites (Task 3 step 4).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-08-memory-and-wiki-phase1.md`.

**Pre-execution gate:** Task 12 dispatches codex to validate this plan. Run that first. If APPROVE, proceed; if REVISE, fix and re-validate once.

Two execution options once validated:

1. **Subagent-Driven (recommended)** — Dispatch fresh subagent per task, two-stage review (spec compliance → code quality), parallel where Group A/B/C allow. Required sub-skill: `superpowers:subagent-driven-development`.
2. **Inline Execution** — Run tasks in this session sequentially with checkpoints. Required sub-skill: `superpowers:executing-plans`.

Which approach?
