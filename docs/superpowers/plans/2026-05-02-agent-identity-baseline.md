# Agent Identity Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in agent identity baseline (persona + blocks + facts + wiki + token-aware history compaction) to the Conexus framework so any agent can become persistent (Ana-style) or stay stateless (worker) via SKILL.md frontmatter alone.

**Architecture:** New `IdentitySection` Pydantic model in SKILL.md frontmatter. New `conexus.core.identity` module providing built-in tools (memory_get/set/list_facts, wiki_read/list/search/write/append_log, block_get/set). New `conexus.core.history` module providing token-budgeted compaction with rolling summary + verbatim recency tail. `build_runtime` auto-registers identity tools and installs prompt-build hook when `identity.enabled=true`. Existing `chat_recent(limit=10)` replaced by `build_history(...)`. `facts` table gains `agent_id` column for multi-agent isolation.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite (additive migration), LiteLLM (cheap model for compaction calls), existing `WikiStore` filesystem markdown.

---

## File Structure

**Create:**
- `src/conexus/core/identity/__init__.py` — module init
- `src/conexus/core/identity/tools.py` — `IdentityTools` class (built-in tool methods)
- `src/conexus/core/identity/blocks.py` — block storage (SQLite-backed mutable text buffers)
- `src/conexus/core/identity/context.py` — assembles identity context block for prompt injection
- `src/conexus/core/history/__init__.py` — module init
- `src/conexus/core/history/compactor.py` — token-budget compactor with rolling summary
- `src/conexus/core/history/summarizer.py` — LLM call to fold messages into summary
- `src/conexus/tests/core/config/test_identity_section.py`
- `src/conexus/tests/core/memory/test_facts_agent_scope.py`
- `src/conexus/tests/core/memory/test_blocks_store.py`
- `src/conexus/tests/core/memory/test_chat_summaries.py`
- `src/conexus/tests/core/identity/test_identity_tools.py`
- `src/conexus/tests/core/identity/test_context_assembly.py`
- `src/conexus/tests/core/history/test_compactor.py`
- `src/conexus/tests/integration/test_identity_baseline_e2e.py`

**Modify:**
- `src/conexus/core/config/skill_loader.py` — add `IdentitySection`, `HistorySection`, `BlockSpec` models; add `identity:` field to `SkillFrontmatter`
- `src/conexus/core/memory/sqlite_store.py` — add `agent_id` column to `facts` (with migration); add `chat_summaries` and `identity_blocks` tables; scope existing fact methods by `agent_id`
- `src/conexus/cli/runner.py` (`build_runtime`) — read identity config, wire `IdentityTools` as second backend, install prompt-build hook
- `src/conexus/core/agent_handler.py` — replace `cfg.include_facts` flag with identity context assembly; use `build_history` instead of `chat_recent`

**Test:**
- All new files above + integration test that loads a SKILL.md with `identity:` block and validates persona + block + wiki-index appear in system prompt.

---

## Task 1: Pydantic schema for IdentitySection

**Files:**
- Modify: `src/conexus/core/config/skill_loader.py:35-46`
- Test: `src/conexus/tests/core/config/test_identity_section.py`

- [ ] **Step 1: Write the failing test**

Create `src/conexus/tests/core/config/test_identity_section.py`:

```python
"""Tests for IdentitySection in SKILL.md frontmatter."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from conexus.core.config.skill_loader import (
    BlockSpec,
    HistorySection,
    IdentitySection,
    SkillFrontmatter,
    parse_skill_file,
)


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "SKILL.md"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_identity_section_defaults_disabled():
    fm = SkillFrontmatter(
        name="x", role="r", goal="g", tools=[],
        llm={"provider": "gemini", "model": "gemini-2.5-flash"},
    )
    assert fm.identity is None


def test_identity_section_full(tmp_path):
    skill = _write(tmp_path, """\
        ---
        name: ana
        role: secretary
        goal: help
        tools: []
        llm: {provider: gemini, model: gemini-2.5-flash}
        identity:
          enabled: true
          blocks:
            user: 500
            scratch: 200
          facts:
            enabled: true
            inject_recent: 5
          wiki:
            dir: ./wiki/ana
            inject_index: true
          history:
            budget_tokens: 4000
            keep_verbatim: 6
            summary_budget: 800
            trigger_pct: 0.80
        ---
        body
    """)
    doc = parse_skill_file(skill)
    ident = doc.frontmatter.identity
    assert ident is not None
    assert ident.enabled is True
    assert ident.blocks["user"].budget_chars == 500
    assert ident.facts.enabled is True
    assert ident.facts.inject_recent == 5
    assert ident.wiki.dir == "./wiki/ana"
    assert ident.wiki.inject_index is True
    assert ident.history.budget_tokens == 4000
    assert ident.history.keep_verbatim == 6


def test_identity_section_minimal(tmp_path):
    skill = _write(tmp_path, """\
        ---
        name: helper
        role: r
        goal: g
        tools: []
        llm: {provider: gemini, model: gemini-2.5-flash}
        identity:
          enabled: true
        ---
        body
    """)
    doc = parse_skill_file(skill)
    ident = doc.frontmatter.identity
    assert ident.enabled is True
    assert ident.blocks == {}
    assert ident.facts.enabled is False
    assert ident.wiki is None
    assert ident.history.budget_tokens == 4000  # default


def test_blocks_accept_int_or_dict(tmp_path):
    skill = _write(tmp_path, """\
        ---
        name: x
        role: r
        goal: g
        tools: []
        llm: {provider: gemini, model: gemini-2.5-flash}
        identity:
          enabled: true
          blocks:
            user: 500
            scratch: {budget_chars: 200, initial: "ready"}
        ---
        body
    """)
    doc = parse_skill_file(skill)
    blocks = doc.frontmatter.identity.blocks
    assert blocks["user"].budget_chars == 500
    assert blocks["user"].initial is None
    assert blocks["scratch"].budget_chars == 200
    assert blocks["scratch"].initial == "ready"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "C:/Users/leandro.theodoro.MN-NTB-LEANDROT/Documents/Agents Team"
uv run pytest src/conexus/tests/core/config/test_identity_section.py -v
```

Expected: ImportError — `BlockSpec`, `HistorySection`, `IdentitySection` not defined.

- [ ] **Step 3: Add Pydantic models to skill_loader.py**

Edit `src/conexus/core/config/skill_loader.py`. Add after `BudgetSection` (line 32), before `SkillFrontmatter` (line 35):

```python
class BlockSpec(BaseModel):
    """A core-memory block — small mutable text buffer pinned in system prompt."""
    budget_chars: int
    initial: str | None = None

    @classmethod
    def coerce(cls, v):
        # Allow `user: 500` (int) shorthand for `user: {budget_chars: 500}`
        if isinstance(v, int):
            return cls(budget_chars=v)
        return v


class FactsSection(BaseModel):
    enabled: bool = False
    inject_recent: int = 0  # 0 = tool-pull only


class WikiSection(BaseModel):
    dir: str
    inject_index: bool = True


class HistorySection(BaseModel):
    budget_tokens: int = 4000
    keep_verbatim: int = 6
    summary_budget: int = 800
    trigger_pct: float = 0.80


class IdentitySection(BaseModel):
    enabled: bool = False
    blocks: dict[str, BlockSpec] = Field(default_factory=dict)
    facts: FactsSection = Field(default_factory=FactsSection)
    wiki: WikiSection | None = None
    history: HistorySection = Field(default_factory=HistorySection)

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        if isinstance(obj, dict) and "blocks" in obj and isinstance(obj["blocks"], dict):
            obj = {**obj, "blocks": {k: BlockSpec.coerce(v) for k, v in obj["blocks"].items()}}
        return super().model_validate(obj, *args, **kwargs)
```

Then add to `SkillFrontmatter` (after line 46):

```python
    identity: IdentitySection | None = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest src/conexus/tests/core/config/test_identity_section.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/conexus/core/config/skill_loader.py src/conexus/tests/core/config/test_identity_section.py
git commit -m "feat(identity): add IdentitySection schema to SKILL.md frontmatter"
```

---

## Task 2: Scope facts table by agent_id

**Files:**
- Modify: `src/conexus/core/memory/sqlite_store.py:11-16, 110-133`
- Test: `src/conexus/tests/core/memory/test_facts_agent_scope.py`

- [ ] **Step 1: Write the failing test**

Create `src/conexus/tests/core/memory/test_facts_agent_scope.py`:

```python
"""Facts table must be scoped per agent_id."""
from __future__ import annotations

import pytest

from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(str(tmp_path / "test.db"))
    s.init_db()
    return s


def test_facts_isolated_per_agent(store):
    store.fact_set("ana", "wake_time", "6h")
    store.fact_set("helper", "wake_time", "8h")
    assert store.fact_get("ana", "wake_time") == "6h"
    assert store.fact_get("helper", "wake_time") == "8h"


def test_facts_list_scoped(store):
    store.fact_set("ana", "k1", "v1")
    store.fact_set("ana", "k2", "v2")
    store.fact_set("helper", "k3", "v3")
    ana_facts = store.facts_list("ana")
    assert len(ana_facts) == 2
    assert {f["key"] for f in ana_facts} == {"k1", "k2"}
    helper_facts = store.facts_list("helper")
    assert len(helper_facts) == 1


def test_facts_recent_returns_newest_first(store):
    store.fact_set("ana", "old", "v")
    store.fact_set("ana", "new", "v")
    recent = store.facts_recent("ana", limit=10)
    assert recent[0]["key"] == "new"
    assert recent[1]["key"] == "old"


def test_facts_migration_preserves_legacy_rows(tmp_path):
    """Pre-existing global facts rows (no agent_id) get bucketed to '_legacy'."""
    import sqlite3
    db_path = tmp_path / "legacy.db"
    # Simulate old schema
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE facts (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO facts (key, value, updated_at) VALUES ('legacy_k', 'legacy_v', '2026-01-01');
    """)
    conn.commit()
    conn.close()
    # Now run init_db — should migrate
    store = SqliteStore(str(db_path))
    store.init_db()
    assert store.fact_get("_legacy", "legacy_k") == "legacy_v"
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest src/conexus/tests/core/memory/test_facts_agent_scope.py -v
```

Expected: FAIL — `fact_set` takes 2 args not 3.

- [ ] **Step 3: Migrate schema + update methods**

Edit `src/conexus/core/memory/sqlite_store.py`. Replace the `facts` table definition in `SCHEMA` (lines 12-16):

```python
CREATE TABLE IF NOT EXISTS facts (
    agent_id    TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (agent_id, key)
);
CREATE INDEX IF NOT EXISTS idx_facts_agent_updated
    ON facts(agent_id, updated_at DESC);
```

Add migration helper. After `_now_iso()` (line 73), add:

```python
def _migrate_facts_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate legacy facts table (no agent_id) to scoped schema."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(facts)").fetchall()]
    if not cols or "agent_id" in cols:
        return  # fresh DB or already migrated
    conn.executescript("""
        ALTER TABLE facts RENAME TO facts_legacy;
        CREATE TABLE facts (
            agent_id    TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (agent_id, key)
        );
        INSERT INTO facts (agent_id, key, value, updated_at)
            SELECT '_legacy', key, value, updated_at FROM facts_legacy;
        DROP TABLE facts_legacy;
        CREATE INDEX IF NOT EXISTS idx_facts_agent_updated
            ON facts(agent_id, updated_at DESC);
    """)
    conn.commit()
```

Update `init_db` (lines 80-88) to call migration before applying schema:

```python
def init_db(self) -> None:
    from conexus.core.memory.handoff_audit import init_handoff_audit
    from conexus.core.memory.tool_audit import init_tool_audit
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    with self.connect() as conn:
        _migrate_facts_v1_to_v2(conn)
        conn.executescript(SCHEMA)
        conn.commit()
        init_handoff_audit(conn)
        init_tool_audit(conn)
```

Replace fact methods (lines 110-133):

```python
# ----- facts -----

def fact_set(self, agent_id: str, key: str, value: str) -> None:
    with self.connect() as conn:
        conn.execute(
            """INSERT INTO facts (agent_id, key, value, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(agent_id, key) DO UPDATE SET value=excluded.value,
                                                       updated_at=excluded.updated_at""",
            (agent_id, key, value, _now_iso()),
        )
        conn.commit()

def fact_get(self, agent_id: str, key: str) -> str | None:
    with self.connect() as conn:
        row = conn.execute(
            "SELECT value FROM facts WHERE agent_id=? AND key=?",
            (agent_id, key),
        ).fetchone()
        return row["value"] if row else None

def facts_list(self, agent_id: str) -> list[dict]:
    with self.connect() as conn:
        rows = conn.execute(
            "SELECT key, value, updated_at FROM facts WHERE agent_id=? ORDER BY key",
            (agent_id,),
        ).fetchall()
        return [dict(r) for r in rows]

def facts_recent(self, agent_id: str, limit: int = 10) -> list[dict]:
    with self.connect() as conn:
        rows = conn.execute(
            """SELECT key, value, updated_at FROM facts
               WHERE agent_id=? ORDER BY updated_at DESC LIMIT ?""",
            (agent_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

def fact_delete(self, agent_id: str, key: str) -> bool:
    with self.connect() as conn:
        cur = conn.execute(
            "DELETE FROM facts WHERE agent_id=? AND key=?",
            (agent_id, key),
        )
        conn.commit()
        return cur.rowcount > 0
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest src/conexus/tests/core/memory/test_facts_agent_scope.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Update existing callers and run full suite**

```bash
uv run pytest src/conexus/tests -v
```

If existing tests fail due to old `fact_get(key)` signature, update them: prefix the agent name. Search for callers:

```bash
grep -rn "fact_set\|fact_get\|facts_list" src/conexus --include="*.py"
```

Update each non-test caller to pass `agent_id`. For places where the agent name isn't obvious, use the agent's name from `cfg.agent_name`.

- [ ] **Step 6: Commit**

```bash
git add src/conexus
git commit -m "feat(memory): scope facts table by agent_id with v1→v2 migration"
```

---

## Task 3: Identity blocks store

**Files:**
- Modify: `src/conexus/core/memory/sqlite_store.py` — add `identity_blocks` table + methods
- Create: `src/conexus/core/identity/blocks.py`
- Test: `src/conexus/tests/core/memory/test_blocks_store.py`

- [ ] **Step 1: Write the failing test**

Create `src/conexus/tests/core/memory/test_blocks_store.py`:

```python
"""Identity blocks: char-budgeted mutable text buffers per (agent_id, name)."""
from __future__ import annotations

import pytest

from conexus.core.identity.blocks import BlockStore, BlockOverBudgetError
from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(str(tmp_path / "blocks.db"))
    s.init_db()
    return BlockStore(s)


def test_block_set_and_get(store):
    store.set("ana", "user", "Leandro, dev pt-BR.", budget_chars=500)
    assert store.get("ana", "user") == "Leandro, dev pt-BR."


def test_block_returns_none_when_missing(store):
    assert store.get("ana", "missing") is None


def test_block_isolated_per_agent(store):
    store.set("ana", "user", "Leandro", budget_chars=100)
    store.set("helper", "user", "Other", budget_chars=100)
    assert store.get("ana", "user") == "Leandro"
    assert store.get("helper", "user") == "Other"


def test_block_rejects_over_budget(store):
    with pytest.raises(BlockOverBudgetError):
        store.set("ana", "user", "x" * 101, budget_chars=100)


def test_block_list_for_agent(store):
    store.set("ana", "user", "u", budget_chars=100)
    store.set("ana", "scratch", "s", budget_chars=100)
    blocks = store.list("ana")
    assert {b["name"] for b in blocks} == {"user", "scratch"}
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest src/conexus/tests/core/memory/test_blocks_store.py -v
```

Expected: ImportError.

- [ ] **Step 3: Add identity_blocks table to SCHEMA**

In `src/conexus/core/memory/sqlite_store.py`, append to `SCHEMA` (before the closing `"""`):

```python
CREATE TABLE IF NOT EXISTS identity_blocks (
    agent_id     TEXT NOT NULL,
    name         TEXT NOT NULL,
    content      TEXT NOT NULL,
    budget_chars INTEGER NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (agent_id, name)
);
```

- [ ] **Step 4: Create BlockStore class**

Create `src/conexus/core/identity/__init__.py`:

```python
"""Agent identity baseline: persona, blocks, facts, wiki integration."""
```

Create `src/conexus/core/identity/blocks.py`:

```python
"""Identity blocks — char-budgeted mutable text buffers pinned in system prompt."""
from __future__ import annotations

from datetime import datetime, timezone

from conexus.core.memory.sqlite_store import SqliteStore


class BlockOverBudgetError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BlockStore:
    def __init__(self, store: SqliteStore):
        self._store = store

    def set(self, agent_id: str, name: str, content: str, budget_chars: int) -> None:
        if len(content) > budget_chars:
            raise BlockOverBudgetError(
                f"block {name!r} content ({len(content)} chars) exceeds budget ({budget_chars})"
            )
        with self._store.connect() as conn:
            conn.execute(
                """INSERT INTO identity_blocks (agent_id, name, content, budget_chars, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(agent_id, name) DO UPDATE SET
                       content=excluded.content,
                       budget_chars=excluded.budget_chars,
                       updated_at=excluded.updated_at""",
                (agent_id, name, content, budget_chars, _now_iso()),
            )
            conn.commit()

    def get(self, agent_id: str, name: str) -> str | None:
        with self._store.connect() as conn:
            row = conn.execute(
                "SELECT content FROM identity_blocks WHERE agent_id=? AND name=?",
                (agent_id, name),
            ).fetchone()
            return row["content"] if row else None

    def list(self, agent_id: str) -> list[dict]:
        with self._store.connect() as conn:
            rows = conn.execute(
                """SELECT name, content, budget_chars, updated_at
                   FROM identity_blocks WHERE agent_id=? ORDER BY name""",
                (agent_id,),
            ).fetchall()
            return [dict(r) for r in rows]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest src/conexus/tests/core/memory/test_blocks_store.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/conexus
git commit -m "feat(identity): add BlockStore for char-budgeted core-memory blocks"
```

---

## Task 4: chat_summaries table for compaction state

**Files:**
- Modify: `src/conexus/core/memory/sqlite_store.py` — add `chat_summaries` table + methods
- Test: `src/conexus/tests/core/memory/test_chat_summaries.py`

- [ ] **Step 1: Write the failing test**

Create `src/conexus/tests/core/memory/test_chat_summaries.py`:

```python
"""Chat summaries — rolling per-(agent, chat) compaction state."""
from __future__ import annotations

import pytest

from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(str(tmp_path / "summaries.db"))
    s.init_db()
    return s


def test_summary_get_returns_none_when_missing(store):
    assert store.summary_get("ana", "chat-1") is None


def test_summary_set_and_get(store):
    store.summary_set("ana", "chat-1", "User asked about Conexus.", covers_until_msg_id=42, token_count=150)
    s = store.summary_get("ana", "chat-1")
    assert s["summary_text"] == "User asked about Conexus."
    assert s["covers_until_msg_id"] == 42
    assert s["token_count"] == 150


def test_summary_replace_on_update(store):
    store.summary_set("ana", "chat-1", "first", covers_until_msg_id=10, token_count=10)
    store.summary_set("ana", "chat-1", "second", covers_until_msg_id=20, token_count=20)
    s = store.summary_get("ana", "chat-1")
    assert s["summary_text"] == "second"
    assert s["covers_until_msg_id"] == 20
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest src/conexus/tests/core/memory/test_chat_summaries.py -v
```

Expected: AttributeError — `summary_get` not defined.

- [ ] **Step 3: Add chat_summaries table + methods**

In `src/conexus/core/memory/sqlite_store.py`, append to `SCHEMA`:

```python
CREATE TABLE IF NOT EXISTS chat_summaries (
    agent_name           TEXT NOT NULL,
    chat_id              TEXT NOT NULL,
    summary_text         TEXT NOT NULL,
    covers_until_msg_id  INTEGER NOT NULL,
    token_count          INTEGER NOT NULL,
    updated_at           TEXT NOT NULL,
    PRIMARY KEY (agent_name, chat_id)
);
```

Add methods to `SqliteStore` class (after `chat_recent`):

```python
def summary_get(self, agent_name: str, chat_id: str) -> dict | None:
    with self.connect() as conn:
        row = conn.execute(
            """SELECT summary_text, covers_until_msg_id, token_count, updated_at
               FROM chat_summaries WHERE agent_name=? AND chat_id=?""",
            (agent_name, chat_id),
        ).fetchone()
        return dict(row) if row else None

def summary_set(
    self,
    agent_name: str,
    chat_id: str,
    summary_text: str,
    covers_until_msg_id: int,
    token_count: int,
) -> None:
    with self.connect() as conn:
        conn.execute(
            """INSERT INTO chat_summaries
                   (agent_name, chat_id, summary_text, covers_until_msg_id, token_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(agent_name, chat_id) DO UPDATE SET
                   summary_text=excluded.summary_text,
                   covers_until_msg_id=excluded.covers_until_msg_id,
                   token_count=excluded.token_count,
                   updated_at=excluded.updated_at""",
            (agent_name, chat_id, summary_text, covers_until_msg_id, token_count, _now_iso()),
        )
        conn.commit()

def chat_after(self, agent_name: str, chat_id: str, after_msg_id: int) -> list[dict]:
    """Fetch all messages with id > after_msg_id, oldest first."""
    with self.connect() as conn:
        rows = conn.execute(
            """SELECT id, role, content, ts FROM chat_history
               WHERE agent_name=? AND id > ? ORDER BY id ASC""",
            (agent_name, after_msg_id),
        ).fetchall()
        return [dict(r) for r in rows]
```

Note: existing `chat_history` schema doesn't have `chat_id` column. For now, we use `agent_name` as the partition and treat the entire history as one logical chat per agent. Multi-chat support deferred. Where the API requires `chat_id`, callers pass a constant like `"default"`.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest src/conexus/tests/core/memory/test_chat_summaries.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/conexus
git commit -m "feat(memory): add chat_summaries table and chat_after query"
```

---

## Task 5: History compactor (token-budget + rolling summary)

**Files:**
- Create: `src/conexus/core/history/__init__.py`
- Create: `src/conexus/core/history/compactor.py`
- Create: `src/conexus/core/history/summarizer.py`
- Test: `src/conexus/tests/core/history/test_compactor.py`

- [ ] **Step 1: Write the failing test**

Create `src/conexus/tests/core/history/test_compactor.py`:

```python
"""Token-budget compactor with rolling summary + verbatim recency tail."""
from __future__ import annotations

import pytest

from conexus.core.config.skill_loader import HistorySection
from conexus.core.history.compactor import HistoryCompactor, build_history
from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(str(tmp_path / "hist.db"))
    s.init_db()
    return s


def _approx_tokens(text: str) -> int:
    """Stub tokenizer: 4 chars ~ 1 token (matches OpenAI's rule of thumb)."""
    return max(1, len(text) // 4)


def test_empty_history_returns_only_persona(store):
    cfg = HistorySection(budget_tokens=4000, keep_verbatim=6, summary_budget=800, trigger_pct=0.80)
    compactor = HistoryCompactor(store, cfg, summarize_fn=lambda old, new: "summary", token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    assert result.summary is None
    assert result.verbatim_messages == []
    assert result.compaction_triggered is False


def test_short_history_no_compaction(store):
    cfg = HistorySection(budget_tokens=4000, keep_verbatim=6, summary_budget=800, trigger_pct=0.80)
    for i in range(3):
        store.chat_append("ana", "user", f"msg-{i}")
    compactor = HistoryCompactor(store, cfg, summarize_fn=lambda old, new: "summary", token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    assert len(result.verbatim_messages) == 3
    assert result.compaction_triggered is False


def test_overflow_triggers_compaction(store):
    """When older messages don't fit budget AND total >80%, compact them."""
    # 100 long messages, each ~200 tokens (800 chars)
    big = "x" * 800
    for _ in range(100):
        store.chat_append("ana", "user", big)
    cfg = HistorySection(budget_tokens=2000, keep_verbatim=6, summary_budget=400, trigger_pct=0.80)
    captured = {"old": None, "new_count": 0}
    def fake_summarize(old, new):
        captured["old"] = old
        captured["new_count"] = len(new)
        return "compacted summary"
    compactor = HistoryCompactor(store, cfg, summarize_fn=fake_summarize, token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    assert result.compaction_triggered is True
    assert result.summary == "compacted summary"
    assert len(result.verbatim_messages) >= 6  # at least the pinned tail
    # Persisted summary
    saved = store.summary_get("ana", "default")
    assert saved["summary_text"] == "compacted summary"


def test_compaction_uses_existing_summary(store):
    """Second compaction folds prior summary into new one."""
    store.summary_set("ana", "default", "prior summary", covers_until_msg_id=5, token_count=100)
    big = "y" * 800
    for _ in range(50):
        store.chat_append("ana", "user", big)
    cfg = HistorySection(budget_tokens=2000, keep_verbatim=6, summary_budget=400, trigger_pct=0.80)
    captured = {}
    def fake_summarize(old, new):
        captured["old"] = old
        return "merged"
    compactor = HistoryCompactor(store, cfg, summarize_fn=fake_summarize, token_fn=_approx_tokens)
    compactor.build("ana", "default")
    assert captured["old"] == "prior summary"


def test_keep_verbatim_always_pinned(store):
    """Last keep_verbatim turns are NEVER summarized away."""
    for i in range(20):
        store.chat_append("ana", "user", f"m{i}")
    cfg = HistorySection(budget_tokens=4000, keep_verbatim=5, summary_budget=400, trigger_pct=0.80)
    compactor = HistoryCompactor(store, cfg, summarize_fn=lambda o, n: "s", token_fn=_approx_tokens)
    result = compactor.build("ana", "default")
    last_5 = [m["content"] for m in result.verbatim_messages[-5:]]
    assert last_5 == ["m15", "m16", "m17", "m18", "m19"]
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest src/conexus/tests/core/history/test_compactor.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement compactor**

Create `src/conexus/core/history/__init__.py`:

```python
"""Token-aware conversation history with rolling summary + verbatim tail."""
```

Create `src/conexus/core/history/summarizer.py`:

```python
"""LLM-backed summarizer for conversation history compaction."""
from __future__ import annotations

from typing import Callable, Sequence


SUMMARIZER_PROMPT_PT = (
    "Atualize o resumo abaixo incorporando as novas mensagens. "
    "Mantenha fatos sobre o usuário, decisões tomadas, e tarefas pendentes. "
    "Limite: {budget} tokens. Responda apenas com o resumo, sem prefácios.\n\n"
    "Resumo atual:\n{old_summary}\n\nNovas mensagens:\n{new_messages}"
)


def format_messages(messages: Sequence[dict]) -> str:
    return "\n".join(f"[{m['role']}] {m['content']}" for m in messages)


def make_summarizer(llm_call: Callable[[str], str], budget_tokens: int) -> Callable[[str | None, list[dict]], str]:
    """Return a summarize_fn(old_summary, new_messages) -> new_summary."""
    def summarize(old_summary: str | None, new_messages: list[dict]) -> str:
        prompt = SUMMARIZER_PROMPT_PT.format(
            budget=budget_tokens,
            old_summary=old_summary or "(vazio)",
            new_messages=format_messages(new_messages),
        )
        return llm_call(prompt).strip()
    return summarize
```

Create `src/conexus/core/history/compactor.py`:

```python
"""Token-budget conversation history with rolling summary + verbatim tail.

Algorithm (Claude-Code-style, scoped down):
  1. Load summary (if any).
  2. Fetch messages after summary.covers_until_msg_id (oldest first).
  3. Pin last `keep_verbatim` turns — always included.
  4. Greedily add older turns (newest-first) until budget exhausted.
  5. If leftover messages exist AND projected usage > trigger_pct → compact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from conexus.core.config.skill_loader import HistorySection
from conexus.core.memory.sqlite_store import SqliteStore


def default_token_fn(text: str) -> int:
    """Approximate: 4 chars per token. Replace with tiktoken if precision needed."""
    return max(1, len(text) // 4)


@dataclass
class HistoryResult:
    summary: Optional[str]
    verbatim_messages: list[dict]
    compaction_triggered: bool = False
    leftover_count: int = 0


class HistoryCompactor:
    def __init__(
        self,
        store: SqliteStore,
        cfg: HistorySection,
        summarize_fn: Callable[[Optional[str], list[dict]], str],
        token_fn: Callable[[str], int] = default_token_fn,
    ):
        self._store = store
        self._cfg = cfg
        self._summarize = summarize_fn
        self._tok = token_fn

    def build(self, agent_name: str, chat_id: str = "default") -> HistoryResult:
        cfg = self._cfg
        summary_row = self._store.summary_get(agent_name, chat_id)
        summary_text = summary_row["summary_text"] if summary_row else None
        covers_until = summary_row["covers_until_msg_id"] if summary_row else 0

        recent = self._store.chat_after(agent_name, chat_id, covers_until)
        if not recent:
            return HistoryResult(summary=summary_text, verbatim_messages=[])

        # Pin last N verbatim
        keep_n = cfg.keep_verbatim
        pinned = recent[-keep_n:] if len(recent) > keep_n else recent
        older = recent[: len(recent) - len(pinned)] if len(recent) > keep_n else []

        # Token budget remaining after summary + pinned
        summary_toks = self._tok(summary_text) if summary_text else 0
        pinned_toks = sum(self._tok(m["content"]) for m in pinned)
        budget_left = cfg.budget_tokens - summary_toks - pinned_toks

        # Greedily add older (newest-first) until budget exhausted
        included: list[dict] = []
        for msg in reversed(older):
            cost = self._tok(msg["content"])
            if cost > budget_left:
                break
            included.insert(0, msg)
            budget_left -= cost

        leftover = older[: len(older) - len(included)]
        verbatim = included + pinned

        # Compaction check
        triggered = False
        if leftover:
            projected = summary_toks + pinned_toks + sum(self._tok(m["content"]) for m in included)
            usage_pct = projected / cfg.budget_tokens
            if usage_pct >= cfg.trigger_pct:
                new_summary = self._summarize(summary_text, leftover)
                # Cap summary to budget — re-summarize if over
                if self._tok(new_summary) > cfg.summary_budget:
                    new_summary = self._summarize(None, [{"role": "system", "content": new_summary}])
                last_id = leftover[-1]["id"]
                self._store.summary_set(
                    agent_name, chat_id, new_summary, last_id, self._tok(new_summary)
                )
                summary_text = new_summary
                triggered = True

        return HistoryResult(
            summary=summary_text,
            verbatim_messages=verbatim,
            compaction_triggered=triggered,
            leftover_count=len(leftover),
        )


def build_history(
    store: SqliteStore,
    agent_name: str,
    cfg: HistorySection,
    summarize_fn: Callable[[Optional[str], list[dict]], str],
    chat_id: str = "default",
    token_fn: Callable[[str], int] = default_token_fn,
) -> HistoryResult:
    """Convenience wrapper for one-shot history assembly."""
    return HistoryCompactor(store, cfg, summarize_fn, token_fn).build(agent_name, chat_id)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest src/conexus/tests/core/history/test_compactor.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/conexus
git commit -m "feat(history): token-budget compactor with rolling summary + verbatim tail"
```

---

## Task 6: IdentityTools (built-in tool methods)

**Files:**
- Create: `src/conexus/core/identity/tools.py`
- Test: `src/conexus/tests/core/identity/test_identity_tools.py`

- [ ] **Step 1: Write the failing test**

Create `src/conexus/tests/core/identity/test_identity_tools.py`:

```python
"""Built-in IdentityTools: memory_*, wiki_*, block_* methods auto-registered when identity.enabled."""
from __future__ import annotations

from pathlib import Path

import pytest

from conexus.core.identity.tools import IdentityTools
from conexus.core.identity.blocks import BlockStore
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


@pytest.fixture
def deps(tmp_path):
    store = SqliteStore(str(tmp_path / "id.db"))
    store.init_db()
    wiki = WikiStore(str(tmp_path / "wiki"))
    blocks = BlockStore(store)
    tools = IdentityTools(
        agent_id="ana",
        store=store,
        wiki=wiki,
        blocks=blocks,
        block_specs={"user": 500, "scratch": 200},
    )
    return tools, store, wiki, blocks


def test_memory_set_and_get(deps):
    tools, _, _, _ = deps
    tools.memory_set(key="wake_time", value="6h")
    assert tools.memory_get(key="wake_time") == {"key": "wake_time", "value": "6h"}


def test_memory_list_facts_returns_recent(deps):
    tools, _, _, _ = deps
    tools.memory_set(key="a", value="1")
    tools.memory_set(key="b", value="2")
    facts = tools.memory_list_facts()
    assert {f["key"] for f in facts} == {"a", "b"}


def test_block_get_set(deps):
    tools, _, _, _ = deps
    tools.block_set(name="user", content="Leandro, dev pt-BR.")
    assert tools.block_get(name="user") == "Leandro, dev pt-BR."


def test_block_set_unknown_block_rejected(deps):
    tools, _, _, _ = deps
    with pytest.raises(ValueError, match="not declared"):
        tools.block_set(name="undeclared", content="x")


def test_wiki_write_read(deps, tmp_path):
    tools, _, _, _ = deps
    tools.wiki_write(path="about.md", content="# About\nLeandro builds Conexus.")
    assert "Leandro builds Conexus" in tools.wiki_read(path="about.md")


def test_wiki_list(deps):
    tools, _, _, _ = deps
    tools.wiki_write(path="a.md", content="a")
    tools.wiki_write(path="b.md", content="b")
    files = tools.wiki_list()
    assert "a.md" in files and "b.md" in files
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest src/conexus/tests/core/identity/test_identity_tools.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement IdentityTools**

Create `src/conexus/core/identity/tools.py`:

```python
"""Built-in identity tools — auto-registered when identity.enabled in SKILL.md.

Tools exposed (each becomes available to the agent via tool calling):
  - memory_get(key) -> {"key", "value"} | None
  - memory_set(key, value) -> {"ok": True}
  - memory_list_facts() -> list[{"key", "value", "updated_at"}]
  - memory_delete(key) -> {"deleted": bool}
  - block_get(name) -> str | None
  - block_set(name, content) -> {"ok": True}
  - block_list() -> list[{"name", "content", "budget_chars"}]
  - wiki_read(path) -> str
  - wiki_list(folder?) -> list[str]
  - wiki_search(query) -> list[{"path", "snippet"}]
  - wiki_write(path, content) -> {"ok": True}
  - wiki_append_log(kind, title, body) -> {"ok": True}
"""
from __future__ import annotations

from typing import Any

from conexus.core.identity.blocks import BlockStore, BlockOverBudgetError
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


class IdentityTools:
    def __init__(
        self,
        agent_id: str,
        store: SqliteStore,
        wiki: WikiStore | None,
        blocks: BlockStore,
        block_specs: dict[str, int],
    ):
        self._agent_id = agent_id
        self._store = store
        self._wiki = wiki
        self._blocks = blocks
        self._block_specs = block_specs  # name -> budget_chars

    # ---- facts ----

    def memory_get(self, key: str) -> dict | None:
        v = self._store.fact_get(self._agent_id, key)
        if v is None:
            return None
        return {"key": key, "value": v}

    def memory_set(self, key: str, value: str) -> dict:
        self._store.fact_set(self._agent_id, key, value)
        return {"ok": True, "key": key}

    def memory_list_facts(self) -> list[dict]:
        return self._store.facts_list(self._agent_id)

    def memory_delete(self, key: str) -> dict:
        return {"deleted": self._store.fact_delete(self._agent_id, key)}

    # ---- blocks ----

    def block_get(self, name: str) -> str | None:
        return self._blocks.get(self._agent_id, name)

    def block_set(self, name: str, content: str) -> dict:
        if name not in self._block_specs:
            raise ValueError(f"block {name!r} not declared in identity.blocks")
        budget = self._block_specs[name]
        try:
            self._blocks.set(self._agent_id, name, content, budget)
        except BlockOverBudgetError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "name": name}

    def block_list(self) -> list[dict]:
        return self._blocks.list(self._agent_id)

    # ---- wiki ----

    def _require_wiki(self) -> WikiStore:
        if self._wiki is None:
            raise RuntimeError("wiki not configured: set identity.wiki.dir in SKILL.md")
        return self._wiki

    def wiki_read(self, path: str) -> str:
        return self._require_wiki().read(path)

    def wiki_list(self, folder: str = "") -> list[str]:
        return self._require_wiki().list(folder)

    def wiki_search(self, query: str) -> list[dict]:
        return self._require_wiki().search(query)

    def wiki_write(self, path: str, content: str) -> dict:
        self._require_wiki().write(path, content)
        return {"ok": True, "path": path}

    def wiki_append_log(self, kind: str, title: str, body: str = "") -> dict:
        self._require_wiki().append_log(kind, title, body)
        return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest src/conexus/tests/core/identity/test_identity_tools.py -v
```

Expected: 6 passed. If wiki methods fail, check `WikiStore` API matches (`read`, `list`, `search`, `write`, `append_log`).

- [ ] **Step 5: Commit**

```bash
git add src/conexus
git commit -m "feat(identity): built-in IdentityTools (memory + blocks + wiki)"
```

---

## Task 7: Identity context assembler (prompt injection)

**Files:**
- Create: `src/conexus/core/identity/context.py`
- Test: `src/conexus/tests/core/identity/test_context_assembly.py`

- [ ] **Step 1: Write the failing test**

Create `src/conexus/tests/core/identity/test_context_assembly.py`:

```python
"""Identity context assembly — formats blocks + recent facts + wiki index for prompt injection."""
from __future__ import annotations

import pytest

from conexus.core.config.skill_loader import (
    BlockSpec,
    FactsSection,
    HistorySection,
    IdentitySection,
    WikiSection,
)
from conexus.core.identity.blocks import BlockStore
from conexus.core.identity.context import assemble_identity_context
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


@pytest.fixture
def setup(tmp_path):
    store = SqliteStore(str(tmp_path / "ctx.db"))
    store.init_db()
    wiki = WikiStore(str(tmp_path / "wiki"))
    wiki.write("about.md", "# About")
    wiki.write("preferences/morning.md", "# Morning")
    blocks = BlockStore(store)
    blocks.set("ana", "user", "Leandro, dev pt-BR.", budget_chars=500)
    store.fact_set("ana", "wake_time", "6h")
    return store, wiki, blocks


def test_returns_empty_when_disabled(setup):
    store, wiki, blocks = setup
    cfg = IdentitySection(enabled=False)
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert ctx == ""


def test_includes_block_when_set(setup):
    store, wiki, blocks = setup
    cfg = IdentitySection(
        enabled=True,
        blocks={"user": BlockSpec(budget_chars=500)},
    )
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert "user" in ctx.lower()
    assert "Leandro, dev pt-BR." in ctx


def test_includes_recent_facts_when_inject_recent(setup):
    store, wiki, blocks = setup
    cfg = IdentitySection(
        enabled=True,
        facts=FactsSection(enabled=True, inject_recent=5),
    )
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert "wake_time" in ctx
    assert "6h" in ctx


def test_omits_facts_when_inject_recent_zero(setup):
    store, wiki, blocks = setup
    cfg = IdentitySection(
        enabled=True,
        facts=FactsSection(enabled=True, inject_recent=0),
    )
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert "wake_time" not in ctx


def test_includes_wiki_index_when_enabled(setup, tmp_path):
    store, wiki, blocks = setup
    cfg = IdentitySection(
        enabled=True,
        wiki=WikiSection(dir=str(tmp_path / "wiki"), inject_index=True),
    )
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert "about.md" in ctx
    assert "preferences/morning.md" in ctx


def test_omits_wiki_index_when_disabled(setup, tmp_path):
    store, wiki, blocks = setup
    cfg = IdentitySection(
        enabled=True,
        wiki=WikiSection(dir=str(tmp_path / "wiki"), inject_index=False),
    )
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert "about.md" not in ctx
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest src/conexus/tests/core/identity/test_context_assembly.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement assembler**

Create `src/conexus/core/identity/context.py`:

```python
"""Assemble identity context block to prepend to system prompt.

Output format (markdown sections, in order):
  ## Sobre o usuário (block: user)
  <block content>

  ## <other blocks>

  ## Fatos recentes
  - key: value

  ## Wiki (índice)
  - path1
  - path2
"""
from __future__ import annotations

from conexus.core.config.skill_loader import IdentitySection
from conexus.core.identity.blocks import BlockStore
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


def assemble_identity_context(
    agent_id: str,
    cfg: IdentitySection,
    store: SqliteStore,
    wiki: WikiStore | None,
    blocks: BlockStore,
) -> str:
    if not cfg.enabled:
        return ""

    sections: list[str] = []

    # Blocks (in declaration order)
    for name in cfg.blocks:
        content = blocks.get(agent_id, name)
        if content:
            sections.append(f"## Block: {name}\n{content}")

    # Recent facts
    if cfg.facts.enabled and cfg.facts.inject_recent > 0:
        recent = store.facts_recent(agent_id, limit=cfg.facts.inject_recent)
        if recent:
            lines = [f"- {f['key']}: {f['value']}" for f in recent]
            sections.append("## Fatos recentes\n" + "\n".join(lines))

    # Wiki index
    if cfg.wiki and cfg.wiki.inject_index and wiki is not None:
        files = wiki.list("")
        if files:
            lines = [f"- {p}" for p in files]
            sections.append("## Wiki (índice)\n" + "\n".join(lines))

    return "\n\n".join(sections)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest src/conexus/tests/core/identity/test_context_assembly.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/conexus
git commit -m "feat(identity): assemble identity context for prompt injection"
```

---

## Task 8: Wire identity into build_runtime

**Files:**
- Modify: `src/conexus/cli/runner.py` (`build_runtime`)
- Modify: `src/conexus/core/agent_handler.py` — add identity context + history compactor hooks

- [ ] **Step 1: Read current build_runtime**

```bash
cat "src/conexus/cli/runner.py"
cat "src/conexus/core/agent_handler.py"
```

Identify the points where:
- Tools are registered (tools_obj parameter)
- system_prompt is constructed
- chat history is fetched (currently `chat_recent(limit=10)`)

- [ ] **Step 2: Add identity wiring to build_runtime**

In `src/conexus/cli/runner.py`, modify `build_runtime` to accept an optional `identity_runtime` param and to pass identity config + assembled context into the handler config.

Add a helper module `src/conexus/cli/identity_runtime.py`:

```python
"""Wire identity config from SKILL.md into runtime components."""
from __future__ import annotations

from pathlib import Path

from conexus.core.config.skill_loader import IdentitySection
from conexus.core.identity.blocks import BlockStore
from conexus.core.identity.tools import IdentityTools
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


class IdentityRuntime:
    """Holds the identity components built once per agent."""
    def __init__(
        self,
        agent_id: str,
        cfg: IdentitySection,
        store: SqliteStore,
        skill_dir: Path,
    ):
        self.agent_id = agent_id
        self.cfg = cfg
        self.store = store
        self.blocks = BlockStore(store)
        self.wiki: WikiStore | None = None
        if cfg.wiki:
            wiki_path = skill_dir / cfg.wiki.dir if not Path(cfg.wiki.dir).is_absolute() else Path(cfg.wiki.dir)
            wiki_path.mkdir(parents=True, exist_ok=True)
            self.wiki = WikiStore(str(wiki_path))
        block_specs = {name: spec.budget_chars for name, spec in cfg.blocks.items()}
        # Seed initial block content if not present
        for name, spec in cfg.blocks.items():
            if spec.initial and self.blocks.get(agent_id, name) is None:
                self.blocks.set(agent_id, name, spec.initial, spec.budget_chars)
        self.tools = IdentityTools(
            agent_id=agent_id,
            store=store,
            wiki=self.wiki,
            blocks=self.blocks,
            block_specs=block_specs,
        )


def build_identity_runtime(
    agent_id: str,
    cfg: IdentitySection | None,
    store: SqliteStore,
    skill_dir: Path,
) -> IdentityRuntime | None:
    if cfg is None or not cfg.enabled:
        return None
    return IdentityRuntime(agent_id, cfg, store, skill_dir)
```

In `src/conexus/cli/runner.py`, in `build_runtime`:

1. After parsing the skill, if `skill.frontmatter.identity` exists, build an `IdentityRuntime` via `build_identity_runtime(...)`.
2. If identity built, merge `identity_runtime.tools` into the tools object — simplest path: pass identity tools as a second backend in `AgentRegistry.register_backend(name, PythonBackend(identity_runtime.tools))`. Caller (`__main__.py`) handles registration; pass `identity_runtime` out of `build_runtime` for the caller to register.
3. Pass `identity_runtime` and `history_cfg` into `AgentHandlerConfig` so `handle_agent_message` can use them.

Returned object becomes:

```python
@dataclass
class AgentRuntime:
    handler_cfg: AgentHandlerConfig
    tools_schema: list[dict]
    identity: IdentityRuntime | None = None  # NEW
```

- [ ] **Step 3: Modify handle_agent_message to use identity context + compactor**

In `src/conexus/core/agent_handler.py`:

1. Add fields to `AgentHandlerConfig`:
   ```python
   identity: "IdentityRuntime | None" = None
   history_cfg: "HistorySection | None" = None
   summarize_fn: "Callable[[Optional[str], list[dict]], str] | None" = None
   ```

2. Replace the `chat_recent(limit=10)` call with `build_history(...)` when `cfg.history_cfg` provided. Compose messages:
   ```python
   if cfg.history_cfg and cfg.summarize_fn:
       result = build_history(store, cfg.agent_name, cfg.history_cfg, cfg.summarize_fn)
       history_msgs = []
       if result.summary:
           history_msgs.append({"role": "system", "content": f"## Resumo de turnos anteriores\n{result.summary}"})
       history_msgs.extend(
           {"role": m["role"], "content": m["content"]} for m in result.verbatim_messages
       )
   else:
       # legacy path
       history_msgs = [...chat_recent...]
   ```

3. Prepend identity context to system prompt:
   ```python
   identity_ctx = ""
   if cfg.identity:
       from conexus.core.identity.context import assemble_identity_context
       identity_ctx = assemble_identity_context(
           cfg.identity.agent_id,
           cfg.identity.cfg,
           cfg.identity.store,
           cfg.identity.wiki,
           cfg.identity.blocks,
       )
   final_system = (identity_ctx + "\n\n" if identity_ctx else "") + cfg.system_prompt
   ```

4. Drop the old `include_facts` flag (or leave for backward compat but mark deprecated).

- [ ] **Step 4: Update CLI registration in `__main__.py`**

When the runtime returns an `IdentityRuntime`, register its tools as a second backend:

```python
runtime = build_runtime(...)
registry.register(name, tools)
if runtime.identity:
    registry.register_backend(name, PythonBackend(runtime.identity.tools))
```

- [ ] **Step 5: Run all unit tests**

```bash
uv run pytest src/conexus/tests -v
```

Fix any breakage from the new `AgentHandlerConfig` fields. Existing tests should still pass because all new fields have defaults.

- [ ] **Step 6: Commit**

```bash
git add src/conexus
git commit -m "feat(identity): wire IdentityRuntime + compactor into build_runtime/handler"
```

---

## Task 9: End-to-end integration test

**Files:**
- Create: `src/conexus/tests/integration/test_identity_baseline_e2e.py`

- [ ] **Step 1: Write the test**

```python
"""End-to-end: SKILL.md with identity → handle_agent_message produces enriched system prompt."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from conexus.cli.identity_runtime import build_identity_runtime
from conexus.core.config.skill_loader import parse_skill_file
from conexus.core.identity.context import assemble_identity_context
from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def skill_path(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text(textwrap.dedent("""\
        ---
        name: ana
        role: secretary
        goal: help
        tools: []
        llm: {provider: gemini, model: gemini-2.5-flash}
        identity:
          enabled: true
          blocks:
            user:
              budget_chars: 500
              initial: "Leandro, dev pt-BR. Acorda 6h."
          facts:
            enabled: true
            inject_recent: 3
          wiki:
            dir: ./wiki
            inject_index: true
        ---
        # Ana
        Você é a Ana.
    """), encoding="utf-8")
    return p


def test_identity_e2e_assembles_full_context(skill_path, tmp_path):
    doc = parse_skill_file(skill_path)
    store = SqliteStore(str(tmp_path / "e2e.db"))
    store.init_db()

    runtime = build_identity_runtime(
        agent_id="ana",
        cfg=doc.frontmatter.identity,
        store=store,
        skill_dir=skill_path.parent,
    )
    assert runtime is not None

    # Seed a wiki page and a fact via the identity tools
    runtime.tools.wiki_write(path="about.md", content="# About\nLeandro builds Conexus.")
    runtime.tools.memory_set(key="meeting_pref", value="morning")

    ctx = assemble_identity_context("ana", doc.frontmatter.identity, store, runtime.wiki, runtime.blocks)

    assert "Leandro, dev pt-BR. Acorda 6h." in ctx  # initial block content
    assert "meeting_pref" in ctx and "morning" in ctx  # recent fact
    assert "about.md" in ctx  # wiki index
```

- [ ] **Step 2: Run test**

```bash
uv run pytest src/conexus/tests/integration/test_identity_baseline_e2e.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Run full suite**

```bash
uv run pytest -v
```

Expected: all green. If anything red, fix before continuing.

- [ ] **Step 4: Commit**

```bash
git add src/conexus
git commit -m "test(identity): end-to-end integration test for identity baseline"
```

---

## Task 10: Migrate Ana to use identity baseline

**Files:**
- Modify: `agents/ana/SKILL.md` (in `conexus-app` repo, NOT framework)
- Modify: `agents/ana/tools.py` (in `conexus-app` repo) — drop redundant memory_*/wiki_* methods

This task happens in the **conexus-app** repo, after a `uv sync` picks up the framework changes.

- [ ] **Step 1: Add identity block to Ana's SKILL.md**

In `C:\Users\leandro.theodoro.MN-NTB-LEANDROT\Documents\conexus-app\agents\ana\SKILL.md`, add to frontmatter:

```yaml
identity:
  enabled: true
  blocks:
    user:
      budget_chars: 500
      initial: "Leandro, builds Conexus framework. Acorda 6h. Casado, 2 filhos. Trabalha em casa. Prefere reuniões de manhã."
  facts:
    enabled: true
    inject_recent: 0       # tool-pull only — keep current Ana behavior
  wiki:
    dir: ./wiki
    inject_index: true     # NEW capability — TOC in prompt
  history:
    budget_tokens: 4000
    keep_verbatim: 6
    summary_budget: 800
    trigger_pct: 0.80
```

Remove from `tools:` list: `memory_get`, `memory_set`, `memory_list_facts`, `wiki_read`, `wiki_list`, `wiki_search`, `wiki_write`, `wiki_append_log`, `wiki_update_index` — these are now built-in via the framework.

Keep: `calendar_*`, `todos_*`. Add: `block_get`, `block_set` if you want Ana to self-edit her user-block.

Update body: remove the "SEMPRE leia `index.md` antes de responder" line — index is now always in prompt.

- [ ] **Step 2: Trim Ana's tools.py**

In `agents/ana/tools.py`, remove the `memory_*` and `wiki_*` methods. They're now provided by `IdentityTools`. Keep calendar + todos.

- [ ] **Step 3: Smoke test**

Send Ana a Telegram message asking something her wiki should know (e.g. "qual é o status do Conexus?"). Verify she answers without first calling `wiki_read` (because index is in prompt — she goes straight to the right page).

- [ ] **Step 4: Commit (in conexus-app repo)**

```bash
cd "C:/Users/leandro.theodoro.MN-NTB-LEANDROT/Documents/conexus-app"
git add agents/ana
git commit -m "feat(ana): migrate to framework identity baseline (drop custom memory/wiki tools)"
```

---

## Self-Review Checklist

After all 10 tasks done:

- [ ] **Spec coverage** — every section of the design (persona, blocks, facts, wiki, history, identity tools, runtime wiring, Ana migration) maps to a task above. ✅
- [ ] **No placeholders** — every "Step 3: implement" includes the actual code. ✅
- [ ] **Type consistency** — `IdentitySection`, `BlockSpec`, `HistorySection`, `IdentityRuntime`, `HistoryCompactor`, `IdentityTools` named consistently throughout. ✅
- [ ] **Migration safety** — facts table migration creates `_legacy` agent bucket; doesn't drop data. ✅
- [ ] **Backward compat** — `AgentHandlerConfig.identity` defaults to None; existing agents (helper, researcher) keep working without identity block. ✅

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-05-02-agent-identity-baseline.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review, fast iteration.

**2. Inline Execution** — execute tasks in this session with checkpoints.

Which approach?
