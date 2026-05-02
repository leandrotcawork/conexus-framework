# Conexus Framework — Phase 0 Hardening Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Conexus framework against security gaps (trifecta, injection, loops) and structural debt (hardcoded wiki paths, unbounded memory, cache thrash) before adding new agents.

**Architecture:** Six targeted patches applied surgically inside existing loop (`handle_agent_message`) and config layer (`SkillFrontmatter`). No new base classes. No new loops. Each task = one atomic Codex unit. Opus reviews after each phase group.

**Tech Stack:** Python 3.11+, SQLite, Pydantic v2, pytest-asyncio, uv, LiteLLM, APScheduler

**Execution model:** Codex implements each task. Opus code-reviewer runs after each phase group. Max 2 Codex retries per task on failure.

**Spec:** `docs/specs/2026-04-16-conexus-framework-design.md`

---

## File Map

Files touched per phase:

| Phase | Files Created | Files Modified |
|-------|--------------|----------------|
| 0 — Schema | `core/config/skill_loader.py` | (extend Pydantic models) |
| 1 — Wiki NS | `main.py` | (remove hardcoded paths) |
| 2 — Trifecta | `core/security/trifecta.py` (new) | `core/agent_handler.py`, `core/messaging/telegram_bot.py` |
| 3 — Cal Sandbox | `core/security/injection.py` (new) | `core/memory/google_calendar.py` |
| 4 — Loop Guard | — | `core/agent_handler.py` |
| 5 — Cache | — | `core/agent_handler.py` |
| 6 — Mem Tiers | `core/memory/memory_jobs.py` (new) | `core/memory/sqlite_store.py`, `main.py` |
| 7 — Agent Dir | — | `core/agent_registry.py` |

---

## Phase Group A — Foundation (Tasks 0–2)

SKILL.md schema extension + per-agent wiki namespace. All later tasks depend on this. **Opus reviews after Task 2.**

---

### Task 0: Extend SkillFrontmatter

**Goal:** Add `capabilities`, `when_to_use`, `cost_tier`, `visibility`, `wiki_root` fields + make tools list accept objects with optional `data_class` tag.

**Files:**
- Modify: `core/config/skill_loader.py`
- Test: `tests/test_skill_loader.py`

**Acceptance Criteria:**
- [ ] `SkillFrontmatter` accepts new optional fields without breaking existing SKILL.md files
- [ ] `tools:` list accepts both plain strings and `{name: str, data_class: str}` objects
- [ ] `SkillFrontmatter.tool_names()` returns `list[str]` (compat with `schema_gen`)
- [ ] `SkillFrontmatter.tool_data_classes()` returns `dict[str, str | None]` mapping name → class
- [ ] All existing `test_skill_loader.py` tests still pass

**Verify:** `uv run pytest tests/test_skill_loader.py -v` → all pass, no warnings

**Steps:**

- [ ] **Step 1: Codex — implement schema changes**

Codex prompt:
```
Extend `core/config/skill_loader.py`.

Current SkillFrontmatter has `tools: list[str]`.

Changes required:
1. Add optional fields to SkillFrontmatter:
   - `capabilities: list[str] = []`
   - `when_to_use: str | None = None`
   - `cost_tier: str | None = None`   # low | medium | high
   - `visibility: str = "user_facing"` # user_facing | internal
   - `wiki_root: str = "wiki"`

2. Change `tools` field to accept both str and dict:
   - New model: `class ToolEntry(BaseModel): name: str; data_class: str | None = None`
   - Field: `tools: list[ToolEntry | str]` — validator normalises str → ToolEntry(name=str)
   - Add method `tool_names(self) -> list[str]` returns [t.name for t in tools]
   - Add method `tool_data_classes(self) -> dict[str, str | None]` returns {t.name: t.data_class for t in tools}

3. Keep backwards compat: existing SKILL.md with `tools: [str, str]` still parses without error.

Write Pydantic v2 validators. Run existing tests — they must all pass.
File: core/config/skill_loader.py
Tests: tests/test_skill_loader.py — add 3 new tests:
  - test_tool_entry_plain_string_normalised
  - test_tool_entry_dict_with_data_class
  - test_skill_new_optional_fields_default
```

- [ ] **Step 2: Verify**

```bash
uv run pytest tests/test_skill_loader.py -v
```
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add core/config/skill_loader.py tests/test_skill_loader.py
git commit -m "feat(schema): extend SkillFrontmatter — capabilities, wiki_root, tool data_class"
```

---

### Task 1: Migrate SKILL.md files to new schema

**Goal:** Update Ana and Pesquisador SKILL.md with `data_class` tags on all tools + new fields. No behaviour change yet — just schema migration.

**Files:**
- Modify: `agents/ana/SKILL.md`
- Modify: `agents/pesquisador/SKILL.md`
- Test: `tests/test_skill_loader.py` (add parse tests for each agent SKILL.md)

**Acceptance Criteria:**
- [ ] Ana SKILL.md parses cleanly with new schema
- [ ] Pesquisador SKILL.md parses cleanly with new schema
- [ ] All tools have correct `data_class`: `private_read` (calendar, memory, facts), `untrusted_read` (web_fetch, web_search, compile_article, youtube_transcript, pdf_extract), `external_write` (wiki_write, wiki_append_log, wiki_update_index, git_sync, todos_add)
- [ ] `capabilities`, `when_to_use`, `cost_tier`, `visibility`, `wiki_root` declared in both

**Verify:** `uv run pytest tests/test_skill_loader.py -v -k "agent"` → pass

**Steps:**

- [ ] **Step 1: Codex — rewrite SKILL.md tools sections**

Codex prompt:
```
Migrate two SKILL.md files to extended schema.

=== agents/ana/SKILL.md ===
Add after `language: pt-BR`:
  capabilities:
    - calendar_management
    - personal_memory
    - todo_management
    - wiki_knowledge
  when_to_use: "User needs calendar, reminders, todos, or personal knowledge management"
  cost_tier: low
  visibility: user_facing
  wiki_root: wiki

Rewrite tools list from plain strings to objects with data_class:
  tools:
    - { name: calendar_list_events,   data_class: private_read }
    - { name: calendar_create_event,  data_class: external_write }
    - { name: calendar_update_event,  data_class: external_write }
    - { name: calendar_delete_event,  data_class: external_write }
    - { name: memory_get,             data_class: private_read }
    - { name: memory_set,             data_class: external_write }
    - { name: memory_list_facts,      data_class: private_read }
    - { name: todos_add,              data_class: external_write }
    - { name: todos_list,             data_class: private_read }
    - { name: todos_mark_done,        data_class: external_write }
    - { name: wiki_read,              data_class: private_read }
    - { name: wiki_list,              data_class: private_read }
    - { name: wiki_search,            data_class: private_read }
    - { name: wiki_write,             data_class: external_write }
    - { name: wiki_append_log,        data_class: external_write }
    - { name: wiki_update_index,      data_class: external_write }

=== agents/pesquisador/SKILL.md ===
Add after `prefix: pesq`:
  capabilities:
    - web_research
    - wiki_curation
    - knowledge_synthesis
  when_to_use: "User asks for deep research, article compilation, or web search on technical topics"
  cost_tier: medium
  visibility: user_facing
  wiki_root: knowledge

Rewrite tools:
  tools:
    - { name: wiki_read,             data_class: private_read }
    - { name: wiki_write,            data_class: external_write }
    - { name: wiki_search,           data_class: private_read }
    - { name: wiki_list,             data_class: private_read }
    - { name: wiki_delete,           data_class: external_write }
    - { name: web_search,            data_class: untrusted_read }
    - { name: web_fetch,             data_class: untrusted_read }
    - { name: youtube_transcript,    data_class: untrusted_read }
    - { name: pdf_extract,           data_class: untrusted_read }
    - { name: raw_save,              data_class: external_write }
    - { name: compile_article,       data_class: untrusted_read }
    - { name: git_sync,              data_class: external_write }

Do not change any other part of either SKILL.md.

Then in tests/test_skill_loader.py add two tests:
  def test_ana_skill_parses_with_new_schema():
      doc = parse_skill_file("agents/ana/SKILL.md")
      assert doc.frontmatter.wiki_root == "wiki"
      assert doc.frontmatter.visibility == "user_facing"
      tool_dc = doc.frontmatter.tool_data_classes()
      assert tool_dc["calendar_list_events"] == "private_read"
      assert tool_dc["wiki_write"] == "external_write"

  def test_pesquisador_skill_parses_with_new_schema():
      doc = parse_skill_file("agents/pesquisador/SKILL.md")
      assert doc.frontmatter.wiki_root == "knowledge"
      assert doc.frontmatter.cost_tier == "medium"
      tool_dc = doc.frontmatter.tool_data_classes()
      assert tool_dc["web_fetch"] == "untrusted_read"
      assert tool_dc["wiki_write"] == "external_write"
```

- [ ] **Step 2: Fix main.py compat — tool_names()**

`main.py` calls `ana_skill.frontmatter.tools` directly for schema gen. After migration, must use `tool_names()`.

Codex prompt:
```
In main.py, replace two usages of `ana_skill.frontmatter.tools` and
`pesq_skill.frontmatter.tools` with `.tool_names()`:

Line ~232:
  _ANA_TOOLS_SCHEMA = _gen_schemas(AnaTools, ana_skill.frontmatter.tool_names())
  _PESQUISADOR_TOOLS_SCHEMA = _gen_schemas(PesquisadorTools, pesq_skill.frontmatter.tool_names())
```

- [ ] **Step 3: Verify**

```bash
uv run pytest tests/test_skill_loader.py -v
```
Expected: all pass including two new agent tests

- [ ] **Step 4: Commit**

```bash
git add agents/ana/SKILL.md agents/pesquisador/SKILL.md tests/test_skill_loader.py main.py
git commit -m "feat(schema): migrate SKILL.md files — data_class tags + capabilities"
```

---

### Task 2: Per-Agent Wiki Namespace

**Goal:** Remove hardcoded `data_dir/wiki` and `data_dir/knowledge` paths from `main.py`. Drive wiki dirs from `SKILL.md.wiki_root`. Each agent gets `data_dir/<agent_name>/<wiki_root>`. Per-agent env var `<AGENT_NAME>_WIKI_REPO`.

**Files:**
- Modify: `main.py`
- Create: `tests/test_wiki_namespace.py`

**Acceptance Criteria:**
- [ ] Ana wiki at `data_dir/ana/wiki/` (was `data_dir/wiki/`)
- [ ] Pesquisador wiki at `data_dir/pesquisador/knowledge/` (was `data_dir/knowledge/`)
- [ ] Env vars: `ANA_WIKI_REPO`, `PESQUISADOR_WIKI_REPO` (old: `KNOWLEDGE_WIKI_REPO`)
- [ ] SSH keys: `ANA_WIKI_DEPLOY_KEY`, `PESQUISADOR_WIKI_DEPLOY_KEY` (old: `GITHUB_WIKI_DEPLOY_KEY`)
- [ ] `main.py` derives path as: `data_dir / agent_name / skill.frontmatter.wiki_root`
- [ ] Missing `wiki_root` → Pydantic default `"wiki"` (covered by Task 0 schema test)
- [ ] Missing `ANA_WIKI_REPO` / `PESQUISADOR_WIKI_REPO` → skip clone, use local dir (no error)
- [ ] Missing deploy key env var → `key_file = None`, no SSH configured (no error)
- [ ] Unit tests prove path derivation formula independently of live env vars

**Verify:**

```bash
uv run pytest tests/test_wiki_namespace.py -v
uv run python -c "from main import amain; print('import ok')"
```
Expected: all pass + `import ok`

**Steps:**

- [ ] **Step 1: Codex — refactor main.py wiki wiring + add tests**

Codex prompt:
```
Refactor wiki path construction in main.py.

Old (hardcoded):
  wiki_dir = data_dir / "wiki"
  knowledge_dir = data_dir / "knowledge"
  ana_wiki_url = os.environ.get("ANA_WIKI_REPO", "")
  knowledge_wiki_url = os.environ.get("KNOWLEDGE_WIKI_REPO", "")
  pesq_deploy_key = os.environ.get("GITHUB_WIKI_DEPLOY_KEY", "")

New (SKILL.md-driven):
  # After skills are loaded (after parse_skill_file calls):
  ana_wiki_dir = data_dir / "ana" / ana_skill.frontmatter.wiki_root
  pesq_wiki_dir = data_dir / "pesquisador" / pesq_skill.frontmatter.wiki_root

  ana_wiki_url = os.environ.get("ANA_WIKI_REPO", "")
  pesq_wiki_url = os.environ.get("PESQUISADOR_WIKI_REPO", "")
  pesq_deploy_key = os.environ.get("PESQUISADOR_WIKI_DEPLOY_KEY", "")

  # WikiStore(ana_wiki_dir, ...) and WikiStore(pesq_wiki_dir, ...)

Keep all clone/pull logic identical — just different path variables.
Keep ANA_WIKI_DEPLOY_KEY for Ana (already correct name).
Remove KNOWLEDGE_WIKI_REPO and GITHUB_WIKI_DEPLOY_KEY references.
Both missing repo URL and missing deploy key → silent skip (current pattern, keep it).
Update print statements to show new paths.

Create tests/test_wiki_namespace.py:
from pathlib import Path
from core.config.skill_loader import SkillFrontmatter

def test_wiki_path_derivation_ana():
    # Simulate what main.py does: data_dir / agent_name / wiki_root
    data_dir = Path("/data")
    wiki_root = "wiki"  # Ana default
    expected = Path("/data/ana/wiki")
    assert data_dir / "ana" / wiki_root == expected

def test_wiki_path_derivation_pesquisador():
    data_dir = Path("/data")
    wiki_root = "knowledge"  # Pesquisador wiki_root
    expected = Path("/data/pesquisador/knowledge")
    assert data_dir / "pesquisador" / wiki_root == expected

def test_wiki_root_default_from_pydantic():
    # SkillFrontmatter.wiki_root defaults to "wiki" when not declared
    fm = SkillFrontmatter(
        name="test", role="r", goal="g", language="pt-BR",
        tools=[], llm={"provider": "gemini", "model": "gemini-2.5-flash"},
    )
    assert fm.wiki_root == "wiki"

def test_missing_repo_url_means_skip_clone():
    # main.py pattern: `if url: _clone_or_pull(...)` — no url = skip
    url = ""  # env var missing
    should_clone = bool(url)
    assert should_clone is False

def test_missing_deploy_key_means_no_ssh():
    key_content = ""  # env var missing
    key_file = None if not key_content else "some_path"
    assert key_file is None
```

- [ ] **Step 2: Verify**

```bash
uv run pytest tests/test_wiki_namespace.py -v
uv run python -c "from main import amain; print('import ok')"
```
Expected: all pass + `import ok`

- [ ] **Step 3: Commit**

```bash
git add main.py tests/test_wiki_namespace.py
git commit -m "feat(wiki): SKILL.md-driven per-agent wiki namespace — remove hardcoded paths"
```

---

> ### Opus Review Gate — Phase Group A
>
> Run `superpowers-extended-cc:code-reviewer` with:
> - Spec section: §4 + §4a of `docs/specs/2026-04-16-conexus-framework-design.md`
> - Changed files: `core/config/skill_loader.py`, `agents/ana/SKILL.md`, `agents/pesquisador/SKILL.md`, `main.py`, `tests/test_skill_loader.py`
> - Check: schema backward compat, path migration correct, no data loss on existing Fly.io volume
>
> Block next phase until Opus approves.

---

## Phase Group B — Security (Tasks 3–5)

P0-1 Trifecta Guard + P0-2 Calendar Injection Sandbox + P0-3 Loop Detection. **Opus reviews after Task 5.**

---

### Task 3: Trifecta Guard

**Goal:** Detect when single turn uses `untrusted_read` tool then attempts `external_write` — abort turn, notify operator via Telegram.

**Files:**
- Create: `core/security/__init__.py`
- Create: `core/security/trifecta.py`
- Modify: `core/agent_handler.py`
- Modify: `core/agent_handler.py` — `AgentHandlerConfig` gains `trifecta_notify: Callable | None`
- Test: `tests/test_trifecta.py`

**Acceptance Criteria:**
- [ ] `TrifectaGuard` tracks data classes seen per turn
- [ ] Violation = `untrusted_read` seen in turn + `external_write` attempted = raise `TrifectaViolation`
- [ ] `handle_agent_message` catches violation → returns warning string → calls `trifecta_notify` if set
- [ ] Turn with only `private_read` + `external_write` = NOT violation (trifecta requires untrusted input)
- [ ] Turn with only `untrusted_read` (no external write) = NOT violation
- [ ] `AgentHandlerConfig.tool_data_classes` populated from `SkillFrontmatter.tool_data_classes()` in `main.py` — wiring proven by integration test that calls a real tool name from SKILL.md and verifies classification
- [ ] Test `test_trifecta_guard_classifies_from_skill_dict` uses actual SKILL.md tool names (`web_fetch` → `untrusted_read`, `wiki_write` → `external_write`) to prove end-to-end classification
- [ ] All existing `test_agent_handler.py` tests still pass

**Verify:** `uv run pytest tests/test_trifecta.py tests/test_agent_handler.py -v` → all pass

**Steps:**

- [ ] **Step 1: Codex — implement TrifectaGuard**

Codex prompt:
```
Create core/security/__init__.py (empty).

Create core/security/trifecta.py:

class TrifectaViolation(Exception):
    def __init__(self, offending_tool: str):
        self.offending_tool = offending_tool
        super().__init__(f"Trifecta violation: {offending_tool} attempted external_write after untrusted_read")

class TrifectaGuard:
    """Tracks data_class per tool call in a single turn.
    
    Violation: turn already saw untrusted_read AND now attempts external_write.
    Call record_call() before executing each tool. Raises TrifectaViolation if violated.
    Reset by creating new instance per turn.
    """
    def __init__(self, tool_data_classes: dict[str, str | None]):
        # tool_data_classes: {tool_name: data_class | None}
        self._tdc = tool_data_classes
        self._saw_untrusted_read = False

    def record_call(self, tool_name: str) -> None:
        dc = self._tdc.get(tool_name)
        if dc == "untrusted_read":
            self._saw_untrusted_read = True
        elif dc == "external_write" and self._saw_untrusted_read:
            raise TrifectaViolation(tool_name)

Create tests/test_trifecta.py with tests:
  - test_no_violation_private_then_external: private_read → external_write → no raise
  - test_no_violation_untrusted_read_only: untrusted_read only → no raise
  - test_violation_untrusted_then_external: untrusted_read → external_write → raises TrifectaViolation
  - test_violation_offending_tool_name: offending_tool attribute correct
  - test_unknown_tool_ignored: tool not in map → no raise
```

- [ ] **Step 2: Codex — wire TrifectaGuard into handle_agent_message**

Codex prompt:
```
Modify core/agent_handler.py:

1. Add field to AgentHandlerConfig:
   tool_data_classes: dict[str, str | None] = field(default_factory=dict)
   trifecta_notify: Callable[[str], Awaitable[None]] | None = None

2. In handle_agent_message, before the tool loop:
   from core.security.trifecta import TrifectaGuard, TrifectaViolation
   guard = TrifectaGuard(cfg.tool_data_classes)

3. Inside the tool_calls loop, before executing each tool:
   try:
       guard.record_call(fn_name)
   except TrifectaViolation as e:
       warn = f"[SEGURANÇA] Violação trifecta: {e.offending_tool} bloqueado neste turno."
       if cfg.trifecta_notify:
           await cfg.trifecta_notify(warn) if inspect.iscoroutinefunction(cfg.trifecta_notify) else cfg.trifecta_notify(warn)
       store.chat_append(cfg.name, "assistant", warn)
       return warn

4. In main.py, wire tool_data_classes into both AgentHandlerConfig:
   _ana_handler_cfg = AgentHandlerConfig(
       ...existing fields...,
       tool_data_classes=ana_skill.frontmatter.tool_data_classes(),
       trifecta_notify=send_to_leandro,
   )
   _pesq_handler_cfg = AgentHandlerConfig(
       ...existing fields...,
       tool_data_classes=pesq_skill.frontmatter.tool_data_classes(),
       trifecta_notify=send_pesq_to_leandro,
   )
```

- [ ] **Step 3: Verify**

```bash
uv run pytest tests/test_trifecta.py tests/test_agent_handler.py -v
```
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add core/security/ core/agent_handler.py main.py tests/test_trifecta.py
git commit -m "feat(security): trifecta guard — block untrusted_read → external_write in same turn"
```

---

### Task 4: Calendar Content Sandbox

**Goal:** Strip/flag injection-like content from Google Calendar event descriptions before they reach LLM context. Addresses OWASP LLM01:2025 + Gemini CVE Jan 2026.

**Files:**
- Create: `core/security/injection.py`
- Modify: `core/memory/google_calendar.py`
- Test: `tests/test_injection.py`

**Acceptance Criteria:**
- [ ] `sanitise_calendar_description(text: str) -> tuple[str, bool]` detects imperative injection patterns
- [ ] Detected content replaced with `[CONTEÚDO REDACTED - possível injeção]`
- [ ] Returns `(sanitised_text, was_flagged: bool)`
- [ ] `GoogleCalendarClient.list_events()` applies sanitiser to each event description
- [ ] Flagged events logged to stderr with event id
- [ ] Patterns detected: "ignore previous", "system:", "SYSTEM:", imperative openers ("You are", "You must", "Forget"), triple-backtick code blocks in descriptions
- [ ] Clean descriptions pass through unchanged

**Verify:** `uv run pytest tests/test_injection.py tests/test_tools_calendar.py -v` → all pass

**Steps:**

- [ ] **Step 1: Codex — implement injection detector**

Codex prompt:
```
Create core/security/injection.py:

import re
import sys

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+previous\s+instructions?", re.IGNORECASE),
    re.compile(r"^(system|user|assistant)\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(you\s+are|you\s+must|forget\s+all|disregard)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"```[\s\S]{20,}```"),   # code blocks with substance
    re.compile(r"<\|(?:im_start|im_end|endoftext)\|>"),  # token injection
]

_REDACTED = "[CONTEÚDO REDACTADO - possível injeção]"

def sanitise_calendar_description(text: str) -> tuple[str, bool]:
    """Return (sanitised, was_flagged). Replaces suspicious content."""
    if not text:
        return text, False
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return _REDACTED, True
    return text, False

Then modify core/memory/google_calendar.py list_events():
After building the event dict, apply:
  from core.security.injection import sanitise_calendar_description
  raw_desc = e.get("description", "")
  clean_desc, flagged = sanitise_calendar_description(raw_desc)
  if flagged:
      print(f"[security] calendar injection flagged event_id={e['id']}", file=sys.stderr, flush=True)
  # use clean_desc in returned dict

Create tests/test_injection.py:
  - test_clean_description_unchanged
  - test_ignore_previous_flagged
  - test_system_colon_flagged
  - test_you_are_flagged
  - test_code_block_flagged
  - test_token_injection_flagged
  - test_empty_string_unchanged
  - test_returns_redacted_string_on_flag
```

- [ ] **Step 2: Verify**

```bash
uv run pytest tests/test_injection.py tests/test_tools_calendar.py -v
```
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add core/security/injection.py core/memory/google_calendar.py tests/test_injection.py
git commit -m "feat(security): calendar content sandbox — strip injection patterns from event descriptions"
```

---

### Task 5: Loop Detection — Circuit Breaker

**Goal:** Track same `(tool_name, args_hash)` repeated calls per turn. 3+ identical calls → circuit break, notify operator, halt turn.

**Files:**
- Modify: `core/agent_handler.py`
- Test: `tests/test_agent_handler.py`

**Acceptance Criteria:**
- [ ] Per-turn counter tracks `(tool_name, args_json_hash)` occurrences
- [ ] Third identical call in same turn → circuit break
- [ ] Circuit break: logs, calls `trifecta_notify` (reuses same channel) with `[LOOP]` prefix, halts turn, returns warning
- [ ] Different args to same tool = NOT circuit break
- [ ] Different tool = NOT circuit break
- [ ] `AgentHandlerConfig.max_identical_calls: int = 3` (configurable)

**Verify:** `uv run pytest tests/test_agent_handler.py -v` → all pass

**Steps:**

- [ ] **Step 1: Codex — add loop counter to handle_agent_message**

Codex prompt:
```
Modify core/agent_handler.py handle_agent_message():

1. Add to AgentHandlerConfig (dataclass field):
   max_identical_calls: int = 3

2. At top of handle_agent_message, before tool loop:
   import hashlib
   _tool_call_counts: dict[str, int] = {}

3. Inside tool_calls loop, after parsing fn_name + fn_args, before executing tool:
   _call_key = f"{fn_name}:{hashlib.md5(json.dumps(fn_args, sort_keys=True).encode()).hexdigest()}"
   _tool_call_counts[_call_key] = _tool_call_counts.get(_call_key, 0) + 1
   if _tool_call_counts[_call_key] >= cfg.max_identical_calls:
       warn = f"[LOOP] {fn_name} chamado {_tool_call_counts[_call_key]}x com mesmos args. Turno interrompido."
       print(warn, flush=True)
       if cfg.trifecta_notify:
           _notify = cfg.trifecta_notify(warn)
           if inspect.iscoroutinefunction(cfg.trifecta_notify):
               await _notify
       store.chat_append(cfg.name, "assistant", warn)
       return warn

Add tests in tests/test_agent_handler.py:
  - test_loop_detection_same_tool_same_args_triggers_circuit_break (3 identical → warns)
  - test_loop_detection_same_tool_different_args_no_break
  - test_loop_detection_two_calls_no_break (threshold at 3)
```

- [ ] **Step 2: Verify**

```bash
uv run pytest tests/test_agent_handler.py -v
```
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add core/agent_handler.py tests/test_agent_handler.py
git commit -m "feat(security): loop detection — circuit break on 3 identical tool+args per turn"
```

---

> ### Opus Review Gate — Phase Group B
>
> Run `superpowers-extended-cc:code-reviewer` with:
> - Spec section: §P0-1, §P0-2, §P0-3
> - Changed files: `core/security/trifecta.py`, `core/security/injection.py`, `core/agent_handler.py`, `core/memory/google_calendar.py`, `tests/test_trifecta.py`, `tests/test_injection.py`
> - Check: trifecta logic correct, injection patterns sufficient, loop counter reset per-turn (not cross-turn), no performance regressions
>
> Block next phase until Opus approves.

---

## Phase Group C — Performance (Task 6)

P0-5 Cache Discipline. Single task, standalone. **Opus reviews after Task 6.**

---

### Task 6: Cache Discipline — BRT Timestamp to Tail

**Goal:** Move BRT timestamp out of cached system prompt prefix into user message tail. Stable prefix = cache hits. Fixes arXiv 2601.06007 pattern.

**Files:**
- Modify: `core/agent_handler.py`

**Acceptance Criteria:**
- [ ] System message = `cfg.system_prompt` only (no timestamp appended)
- [ ] First user message ends with `\n\nData/hora atual (BRT): {timestamp}` (was appended to system)
- [ ] All existing `test_agent_handler.py` tests still pass
- [ ] No functional behaviour change — LLM still receives same timestamp, just in user message

**Verify:** `uv run pytest tests/test_agent_handler.py -v` → all pass

**Steps:**

- [ ] **Step 1: Codex — move timestamp**

Codex prompt:
```
In core/agent_handler.py handle_agent_message():

Current:
  system = cfg.system_prompt + f"\n\nData/hora atual (BRT): {now_brt.strftime('%Y-%m-%d %H:%M %Z')}"
  messages = [
      {"role": "system", "content": system},
      {"role": "user", "content": "\n\n".join(user_parts)},
  ]

New:
  system = cfg.system_prompt   # stable — no timestamp
  brt_line = f"Data/hora atual (BRT): {now_brt.strftime('%Y-%m-%d %H:%M %Z')}"
  user_parts.append(brt_line)  # timestamp goes to end of user message
  messages = [
      {"role": "system", "content": system},
      {"role": "user", "content": "\n\n".join(user_parts)},
  ]

Update test assertions in tests/test_agent_handler.py that check system message content
to not expect timestamp there. Add assertion that user message contains the BRT string.
```

- [ ] **Step 2: Verify**

```bash
uv run pytest tests/test_agent_handler.py -v
```
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add core/agent_handler.py tests/test_agent_handler.py
git commit -m "perf(cache): move BRT timestamp to user message tail — stable system prompt prefix"
```

---

> ### Opus Review Gate — Phase Group C
>
> Run `superpowers-extended-cc:code-reviewer` with:
> - Spec section: §P0-5
> - Changed file: `core/agent_handler.py`
> - Check: timestamp still reaches LLM, system prompt truly stable between turns, test coverage adequate
>
> Block next phase until Opus approves.

---

## Phase Group D — Memory (Tasks 7–8)

P0-4 Memory Tiers L0/L1/L2 schema + demotion job. **Opus reviews after Task 8.**

---

### Task 7: Memory Tier Schema — L0/L1

**Goal:** Add `session_summaries` table (L1). Add `chat_history` retention window helpers. No L0 data deleted yet — just schema + methods.

**Files:**
- Modify: `core/memory/sqlite_store.py`
- Test: `tests/test_sqlite_store.py`

**Acceptance Criteria:**
- [ ] `session_summaries` table created by `init_db()` (idempotent)
- [ ] `SqliteStore.summary_insert(agent_name, content, period_start, period_end)` → inserts row
- [ ] `SqliteStore.summary_list(agent_name, limit=50)` → list of dicts
- [ ] `SqliteStore.chat_purge_before(agent_name, cutoff_iso)` → deletes L0 older than cutoff, returns count
- [ ] `SqliteStore.summary_purge_before(agent_name, cutoff_iso)` → deletes L1 older than cutoff, returns count
- [ ] All existing `test_sqlite_store.py` tests still pass

**Verify:** `uv run pytest tests/test_sqlite_store.py -v` → all pass

**Steps:**

- [ ] **Step 1: Codex — extend sqlite_store.py**

Codex prompt:
```
Extend core/memory/sqlite_store.py:

1. Add to SCHEMA string (after existing tables):
CREATE TABLE IF NOT EXISTS session_summaries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name   TEXT NOT NULL,
    content      TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_summaries_agent_ts
    ON session_summaries(agent_name, created_at);

2. Add methods to SqliteStore class:

def summary_insert(self, agent_name: str, content: str, period_start: str, period_end: str) -> int:
    with self.connect() as conn:
        cur = conn.execute(
            "INSERT INTO session_summaries (agent_name, content, period_start, period_end, created_at) VALUES (?, ?, ?, ?, ?)",
            (agent_name, content, period_start, period_end, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid

def summary_list(self, agent_name: str, limit: int = 50) -> list[dict]:
    with self.connect() as conn:
        rows = conn.execute(
            "SELECT id, agent_name, content, period_start, period_end, created_at FROM session_summaries WHERE agent_name=? ORDER BY created_at DESC LIMIT ?",
            (agent_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]

def chat_purge_before(self, agent_name: str, cutoff_iso: str) -> int:
    with self.connect() as conn:
        cur = conn.execute(
            "DELETE FROM chat_history WHERE agent_name=? AND ts < ?",
            (agent_name, cutoff_iso),
        )
        conn.commit()
        return cur.rowcount

def summary_purge_before(self, agent_name: str, cutoff_iso: str) -> int:
    with self.connect() as conn:
        cur = conn.execute(
            "DELETE FROM session_summaries WHERE agent_name=? AND created_at < ?",
            (agent_name, cutoff_iso),
        )
        conn.commit()
        return cur.rowcount

Add tests in tests/test_sqlite_store.py:
  - test_summary_insert_and_list
  - test_chat_purge_before_deletes_old_only
  - test_summary_purge_before_deletes_old_only
  - test_summary_list_returns_newest_first
```

- [ ] **Step 2: Verify**

```bash
uv run pytest tests/test_sqlite_store.py -v
```
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add core/memory/sqlite_store.py tests/test_sqlite_store.py
git commit -m "feat(memory): add L1 session_summaries table + purge helpers for memory tier demotion"
```

---

### Task 8: Memory Demotion Job (L0→L1 weekly cron)

**Goal:** Weekly cron: summarise L0 chat older than 30d via LLM → insert L1 → delete L0. L1 older than 180d → distil key facts → append to L2 wiki → delete L1.

**Retention constants (hardcoded, source of truth in `memory_jobs.py`):**
- L0 retention: **30 days** — rows with `ts < now - 30d` are candidates
- L1 retention: **180 days** — summaries with `created_at < now - 180d` are candidates

**Files:**
- Create: `core/memory/memory_jobs.py`
- Modify: `main.py` (register job in scheduler)
- Test: `tests/test_memory_jobs.py`

**Acceptance Criteria:**
- [ ] `make_l0_demotion_job(store, llm_acomplete, agent_name)` → async callable (no wiki_store arg — L1 is SQLite, not wiki)
- [ ] `make_l1_demotion_job(store, llm_acomplete, agent_name, wiki)` → async callable (wiki needed for L2 append)
- [ ] L0 job: all rows older than 30d for `agent_name` summarised in single LLM call (not week-by-week — simpler, sufficient for current corpus)
- [ ] L0 job inserts L1 via `summary_insert` BEFORE purging L0 — order prevents data loss on crash
- [ ] L0 job purges via `chat_purge_before(agent_name, cutoff)` — agent-scoped, no cross-agent deletion
- [ ] L1 job: summaries older than 180d distilled to wiki `memory/long_term_facts.md` (append, never overwrite)
- [ ] L1 job inserts wiki BEFORE purging L1 — same crash-safety order
- [ ] Empty store → job exits cleanly, no LLM call, no error (explicit no-op branch)
- [ ] Jobs idempotent: running twice in same window demotes 0 rows second time (cutoff already past)
- [ ] Scheduler crons in `America/Sao_Paulo` (BRT) — `ConexusScheduler` already sets tz, cron strings are local time: L0 at `"0 3 * * 0"` (Sun 03:00 BRT), L1 at `"0 4 1 * *"` (1st of month 04:00 BRT)
- [ ] Tests use `freezegun` to pin `datetime.now()` + mock `llm_acomplete` with `async def mock_llm(p): return "Resumo."`

**Verify:** `uv run pytest tests/test_memory_jobs.py -v` → all pass

**Steps:**

- [ ] **Step 1: Codex — implement memory_jobs.py**

Codex prompt:
```
Create core/memory/memory_jobs.py:

from __future__ import annotations
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable
from core.memory.sqlite_store import SqliteStore
from core.memory.wiki_store import WikiStore

_UTC = timezone.utc

def _cutoff_iso(days: int) -> str:
    return (datetime.now(_UTC) - timedelta(days=days)).isoformat()

# L0 job demotes using _L0_RETENTION_DAYS, L1 job uses _L1_RETENTION_DAYS
# Constants defined at module level for easy auditing

_L0_RETENTION_DAYS = 30   # L0 chat_history retention window
_L1_RETENTION_DAYS = 180  # L1 session_summaries retention window

def make_l0_demotion_job(
    store: SqliteStore,
    llm_acomplete: Callable[[str], Awaitable[str]],
    agent_name: str,
) -> Callable[[], Awaitable[None]]:
    """Returns async job: demote L0 chat older than 30d to L1 summaries."""
    async def _job() -> None:
        cutoff = _cutoff_iso(_L0_RETENTION_DAYS)
        # Fetch old turns (agent-scoped — no cross-agent deletion)
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT id, role, content, ts FROM chat_history WHERE agent_name=? AND ts < ? ORDER BY ts",
                (agent_name, cutoff),
            ).fetchall()
        if not rows:
            print(f"[memory_demotion] {agent_name}: no L0 rows to demote", flush=True)
            return

        # Build summary prompt from all old turns (single call, not week-by-week)
        turns_text = "\n".join(f"{r['ts']} {r['role']}: {r['content']}" for r in rows)
        period_start = rows[0]["ts"]
        period_end = rows[-1]["ts"]
        prompt = (
            f"Você é o assistente de memória do agente {agent_name}. "
            f"Abaixo estão conversas do período {period_start[:10]} a {period_end[:10]}. "
            f"Resuma os fatos importantes, decisões tomadas, e contexto relevante em ≤500 palavras. "
            f"Seja conciso e factual.\n\n{turns_text}"
        )
        summary = await llm_acomplete(prompt)
        # Insert L1 BEFORE deleting L0 — crash-safe order
        store.summary_insert(agent_name, summary, period_start, period_end)
        deleted = store.chat_purge_before(agent_name, cutoff)
        print(f"[memory_demotion] {agent_name}: L0→L1 done. {deleted} turns deleted, summary inserted.", flush=True)
    return _job

def make_l1_demotion_job(
    store: SqliteStore,
    llm_acomplete: Callable[[str], Awaitable[str]],
    agent_name: str,
    wiki: WikiStore,
) -> Callable[[], Awaitable[None]]:
    """Returns async job: demote L1 summaries older than 180d to L2 wiki."""
    async def _job() -> None:
        cutoff = _cutoff_iso(_L1_RETENTION_DAYS)
        summaries = store.summary_list(agent_name, limit=500)
        old = [s for s in summaries if s["created_at"] < cutoff]
        if not old:
            print(f"[memory_demotion] {agent_name}: no L1 rows to demote", flush=True)
            return

        combined = "\n\n---\n\n".join(
            f"Período {s['period_start'][:10]}–{s['period_end'][:10]}:\n{s['content']}"
            for s in old
        )
        prompt = (
            f"Abaixo estão resumos de sessões antigas do agente {agent_name}. "
            f"Extraia apenas fatos permanentes, preferências duradouras, e decisões de longo prazo. "
            f"Formato: lista de bullets em markdown. Máximo 300 palavras.\n\n{combined}"
        )
        facts_md = await llm_acomplete(prompt)
        # Append to L2 wiki
        target = "memory/long_term_facts.md"
        try:
            existing = wiki.read(target)
        except Exception:
            existing = "# Fatos de Longo Prazo\n\n"
        from datetime import date
        # Write wiki BEFORE purging L1 — crash-safe order
        wiki.write(target, existing + f"\n## {date.today().isoformat()}\n\n{facts_md}\n")
        deleted = store.summary_purge_before(agent_name, cutoff)
        print(f"[memory_demotion] {agent_name}: L1→L2 done. {deleted} summaries distilled to wiki.", flush=True)
    return _job

Create tests/test_memory_jobs.py:
Use tmp_path fixture for SqliteStore and WikiStore.
Mock llm_acomplete with: async def mock_llm(prompt): return "Resumo mock."

Tests:
  - test_l0_demotion_no_rows_is_noop: empty DB → job runs, no L1 inserted
  - test_l0_demotion_old_rows_demoted: insert chat rows with ts 40 days ago → job runs → L1 inserted, L0 deleted
  - test_l0_demotion_recent_rows_skipped: rows 5 days ago → job runs → L0 NOT deleted
  - test_l1_demotion_no_rows_is_noop: empty summaries → job runs cleanly
  - test_l1_demotion_old_summaries_to_wiki: insert L1 row 200 days ago → job runs → wiki file created, L1 deleted
```

- [ ] **Step 2: Codex — wire jobs into main.py scheduler**

Codex prompt:
```
In main.py, import and wire memory demotion jobs:

from core.memory.memory_jobs import make_l0_demotion_job, make_l1_demotion_job

After scheduler.add_job calls for pesquisador, add:
# L0 demotion: SQLite only — no wiki arg
scheduler.add_job(JobSpec("ana", "l0_demotion", "0 3 * * 0",
                          make_l0_demotion_job(store, ana_llm.acomplete, "ana")))
scheduler.add_job(JobSpec("pesquisador", "l0_demotion", "0 3 * * 0",
                          make_l0_demotion_job(store, pesq_llm.acomplete, "pesquisador")))
# L1 demotion: needs wiki for L2 append
scheduler.add_job(JobSpec("ana", "l1_demotion", "0 4 1 * *",
                          make_l1_demotion_job(store, ana_llm.acomplete, "ana", wiki)))
scheduler.add_job(JobSpec("pesquisador", "l1_demotion", "0 4 1 * *",
                          make_l1_demotion_job(store, pesq_llm.acomplete, "pesquisador", knowledge_wiki)))
```

- [ ] **Step 3: Verify**

```bash
uv run pytest tests/test_memory_jobs.py -v
uv run python -c "from main import amain; print('import ok')"
```
Expected: all pass + `import ok`

- [ ] **Step 4: Commit**

```bash
git add core/memory/memory_jobs.py tests/test_memory_jobs.py main.py
git commit -m "feat(memory): L0→L1→L2 demotion jobs — weekly summary, monthly wiki distillation"
```

---

> ### Opus Review Gate — Phase Group D
>
> Run `superpowers-extended-cc:code-reviewer` with:
> - Spec section: §P0-4
> - Changed files: `core/memory/sqlite_store.py`, `core/memory/memory_jobs.py`, `main.py`, `tests/test_sqlite_store.py`, `tests/test_memory_jobs.py`
> - Check: L0 purge correct (only old rows), L1 distillation doesn't lose info, wiki append idempotent on restart, scheduler crons in BRT
>
> Block next phase until Opus approves.

---

## Phase Group E — Agent Directory (Task 9)

P0-6 Agent Directory. **Opus reviews after Task 9.**

---

### Task 9: Agent Directory — AgentRegistry.describe_agents()

**Goal:** `AgentRegistry` can describe all registered agents (capabilities, when_to_use, cost_tier, visibility) for PM routing. Also validate MCP whitelist config.

**Files:**
- Modify: `core/agent_registry.py`
- Create: `core/config/mcp_whitelist.py`
- Create: `config/mcp_whitelist.yaml` (minimal example)
- Test: `tests/test_agent_registry.py`

**Acceptance Criteria:**
- [ ] `AgentRegistry.register()` accepts optional `skill_frontmatter: SkillFrontmatter` param
- [ ] `AgentRegistry.describe_agents()` returns `list[dict]` with keys: `name`, `capabilities`, `when_to_use`, `cost_tier`, `visibility`
- [ ] Agents registered without frontmatter return empty capabilities list + `when_to_use=None`
- [ ] `load_mcp_whitelist(path)` reads YAML, returns dict of `{server_name: {tools: list[str]}}`. Raises `ValueError` on unknown keys.
- [ ] `config/mcp_whitelist.yaml` exists with example entry
- [ ] All existing `test_agent_registry.py` tests still pass

**Verify:** `uv run pytest tests/test_agent_registry.py -v` → all pass

**Steps:**

- [ ] **Step 1: Codex — extend AgentRegistry + MCP whitelist loader**

Codex prompt:
```
Modify core/agent_registry.py:

1. Import at top: from core.config.skill_loader import SkillFrontmatter

2. Change register() signature:
   def register(self, agent_name: str, tools: Any, frontmatter: SkillFrontmatter | None = None) -> None:
       self._tools[agent_name] = tools
       self._frontmatters[agent_name] = frontmatter  # new dict: self._frontmatters: dict[str, SkillFrontmatter | None] = {}

3. Add method:
   def describe_agents(self) -> list[dict]:
       result = []
       for name in self._tools:
           fm = self._frontmatters.get(name)
           result.append({
               "name": name,
               "capabilities": fm.capabilities if fm else [],
               "when_to_use": fm.when_to_use if fm else None,
               "cost_tier": fm.cost_tier if fm else None,
               "visibility": fm.visibility if fm else "user_facing",
           })
       return result

Create core/config/mcp_whitelist.py:
from pathlib import Path
import yaml

def load_mcp_whitelist(path: str | Path) -> dict:
    """Returns {server_name: {tools: [str], ...}}. Raises ValueError on bad schema."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError("mcp_whitelist.yaml must be a dict")
    for server, cfg in data.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"mcp_whitelist.yaml[{server}] must be a dict")
        if "tools" not in cfg:
            raise ValueError(f"mcp_whitelist.yaml[{server}] missing 'tools' key")
    return data

Create config/mcp_whitelist.yaml:
# Curated MCP server whitelist. No auto-install. Add servers explicitly.
# example_server:
#   tools:
#     - tool_name_1
#     - tool_name_2
#   description: "What this server provides"

Update main.py registry.register() calls to pass frontmatter:
  registry.register("ana", ana_tools, ana_skill.frontmatter)
  registry.register("pesquisador", pesq_tools, pesq_skill.frontmatter)

Add tests in tests/test_agent_registry.py:
  - test_describe_agents_returns_capabilities
  - test_describe_agents_no_frontmatter_returns_defaults
  - test_mcp_whitelist_loads_valid_yaml
  - test_mcp_whitelist_rejects_missing_tools_key
```

- [ ] **Step 2: Verify**

```bash
uv run pytest tests/test_agent_registry.py -v
```
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add core/agent_registry.py core/config/mcp_whitelist.py config/mcp_whitelist.yaml tests/test_agent_registry.py main.py
git commit -m "feat(registry): agent directory — describe_agents() + MCP whitelist loader"
```

---

> ### Opus Review Gate — Phase Group E
>
> Run `superpowers-extended-cc:code-reviewer` with:
> - Spec section: §P0-6
> - Changed files: `core/agent_registry.py`, `core/config/mcp_whitelist.py`, `config/mcp_whitelist.yaml`
> - Check: describe_agents stable under concurrent registration, whitelist loader safe against malformed YAML, main.py wiring correct
>
> Block next phase until Opus approves.

---

## Phase Group F — Final Integration (Task 10)

Full suite pass + KPI check. **Opus reviews final state before Phase 1.**

---

### Task 10: Full Suite + KPI Verification

**Goal:** All tests pass. Core coverage ≥ 80%. Each Phase 0 security module individually verified.

**Files:**
- None new — verify only

**Acceptance Criteria:**
- [ ] `uv run pytest` → 0 failures, 0 errors, 0 unexpected skips
- [ ] `uv run pytest --cov=core --cov-report=term-missing` → TOTAL line shows ≥ 80%
- [ ] Each required test file passes independently (see Step 1)
- [ ] Compile check clean on all new files (see Step 2)
- [ ] `uv run python -c "from main import amain; print('ok')"` → `ok`

**Verify:**

**Step 1 — Individual suite verification (must all pass):**

```bash
uv run pytest tests/test_skill_loader.py -v       # Task 0 + 1: schema
uv run pytest tests/test_wiki_namespace.py -v     # Task 2: path derivation
uv run pytest tests/test_trifecta.py -v           # Task 3: trifecta guard
uv run pytest tests/test_injection.py -v          # Task 4: calendar sandbox
uv run pytest tests/test_agent_handler.py -v      # Task 3+5+6: handler integration
uv run pytest tests/test_sqlite_store.py -v       # Task 7: memory schema
uv run pytest tests/test_memory_jobs.py -v        # Task 8: demotion jobs
uv run pytest tests/test_agent_registry.py -v     # Task 9: agent directory
```
Expected: all pass.

**Step 2 — Compile check:**

```bash
uv run python -m py_compile \
  core/config/skill_loader.py \
  core/security/trifecta.py \
  core/security/injection.py \
  core/memory/memory_jobs.py \
  core/agent_registry.py \
  main.py
```
Expected: no output (no errors).

**Step 3 — Coverage:**

```bash
uv run pytest --cov=core --cov-report=term-missing 2>&1 | grep "TOTAL"
```
Expected: `TOTAL ... 80%` or higher.

**Step 4 — Full suite:**

```bash
uv run pytest -v 2>&1 | tail -5
```
Expected: `N passed` with 0 failed.

**Step 5 — Commit:**

```bash
git commit -m "chore: Phase 0 complete — all tests pass, coverage ≥ 80%"
```

---

> ### Final Opus Review Gate — Phase 0 Complete
>
> Run `superpowers-extended-cc:code-reviewer` with:
> - Full diff of all Phase 0 changes vs `main` branch
> - Spec: full `docs/specs/2026-04-16-conexus-framework-design.md` Phase 0 section
> - Check: every P0-1 through P0-6 requirement addressed, no regressions, framework contract unchanged, KPIs measurable
>
> After approval: merge to main. Phase 1 planning begins.

---

## KPI Checklist (Phase 0 Exit)

| Metric | Target | How to Check |
|--------|--------|-------------|
| Trifecta guard coverage | 100% `untrusted_read` tools tagged | `grep data_class agents/*/SKILL.md` |
| Calendar sandbox | All `list_events` output sanitised | `test_injection.py` |
| Loop detection | Circuit break at 3 identical calls | `test_agent_handler.py` |
| Cache discipline | BRT timestamp in user msg, not system | `test_agent_handler.py` |
| L0→L1 demotion job | Registered + passing | `test_memory_jobs.py` |
| Agent directory | `describe_agents()` works | `test_agent_registry.py` |
| Core test coverage | ≥ 80% | `pytest --cov=core` |
| New agent time-to-wire | < 30 min | Walkthrough against SKILL.md spec |

---

*Spec: `docs/specs/2026-04-16-conexus-framework-design.md`*
*Phase 1 plan: write after Phase 0 merged and stable on Fly.io.*
