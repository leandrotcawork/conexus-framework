# Phase 9 — Multi-Agent Runtime Activation + Replay + MCPProducer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activate the multi-agent loop end-to-end (LLM-emitted `delegate_to_<agent>`, context-mode trimming, return-on stack), promote Trifecta trust-clear to an auditable operation, ship deterministic Replay against frozen traces, expose Conexus tools to Claude Code via MCPProducer, and harden the MCP stdio backend.

**Architecture:**
- Phase 8 shipped the team substrate (`Handoff`, `HandoffRouter`, `BudgetCascader`, cross-agent `TrifectaGuard`, `handoff_audit` table). Phase 9 *consumes* those primitives inside the agent loop. The LLM emits a `delegate_to_<agent>` tool call → handler builds a `Handoff` → `HandoffRouter.route()` resolves target → loop swaps `AgentHandlerConfig` (with trimmed transcript + `incoming_handoff`) and recurses, then returns to caller on `return_on` text or natural reply.
- Replay is deterministic: a new `tool_audit` table records every tool call (timestamps suppressed); `replay()` reads `handoff_audit` + `tool_audit` for a session and re-routes through current pack versions, asserting equality with recorded outcomes.
- MCPProducer is a separate FastMCP server exposing wiki + Conexus tools over stdio (Phase 9 stdio only — Streamable HTTP deferred to a future phase per spec §1.7 hardening).

**Tech Stack:** Python 3.13, pydantic v2, asyncio, sqlite3 (stdlib), `fastmcp>=0.5` (new dep), AST walker (stdlib `ast`), `uv` for deps, `pytest-asyncio` already present.

---

## File Structure

**New files:**
- `src/conexus/core/team/delegate_tool.py` — builds `delegate_to_<agent>` LLM tool schema for a TeamRegistry; parses tool args → `Handoff`.
- `src/conexus/core/team/transcript.py` — `trim_transcript(messages, mode)` for `full|last_message|summary` context modes.
- `src/conexus/core/memory/tool_audit.py` — `tool_audit` SQLite table + `record_tool_call(conn, session_id, agent, tool, args, result, outcome)`.
- `src/conexus/core/team/replay.py` — `replay_session(conn, session_id, registry, packs) -> ReplayReport`.
- `src/conexus/core/mcp/__init__.py` — package marker.
- `src/conexus/core/mcp/producer.py` — FastMCP server factory + tool registration + bearer auth.
- `src/conexus/tests/test_framework_delegate_tool.py`
- `src/conexus/tests/test_framework_transcript.py`
- `src/conexus/tests/test_framework_team_loop.py` — integration: full delegate → return cycle.
- `src/conexus/tests/test_framework_team_loop_termination.py` — termination_text + max_parallel_members.
- `src/conexus/tests/test_framework_trust_clear.py`
- `src/conexus/tests/test_framework_tool_audit.py`
- `src/conexus/tests/test_framework_replay.py`
- `src/conexus/tests/test_framework_mcp_producer.py`
- `src/conexus/tests/test_framework_mcp_stdio_correlation.py`
- `src/conexus/tests/test_framework_pip_install.py` — smoke + deployment field round-trip (T-034).

**Modified files:**
- `src/conexus/core/team/handoff.py` — replace `trust_boundary_cleared: bool` with `trust_boundary_cleared: str | None` (reason or None).
- `src/conexus/core/team/team_pack.py` — add `max_parallel_members: int = 1` to `TeamPolicy`.
- `src/conexus/core/team/handoff_router.py` — adapt audit `trust_cleared` column write to bool(reason is not None) for back-compat.
- `src/conexus/core/trifecta/guard.py` — add `clear_boundary(reason: str)` method; persist reason on guard.
- `src/conexus/core/agent_handler.py` — wire `delegate_to_<agent>` tool dispatch + context_mode + return_on + termination_text + max_parallel_members.
- `src/conexus/core/backends/mcp_stdio_backend.py` — JSON-RPC id correlation reader; pending requests dict.
- `src/conexus/core/memory/sqlite_store.py` — call `init_tool_audit` from `init_db()`.
- `src/conexus/cli/__main__.py` — add `replay <db> --session <id>` + `mcp-server <pack>` subcommands.
- `pyproject.toml` — add `fastmcp>=0.5`.

**Reference files (DO NOT MODIFY unless task says so):**
- `src/conexus/core/team/handoff_router.py` (router resolution logic)
- `src/conexus/core/team/team_registry.py` (read-only TeamRegistry view)
- `src/conexus/core/agent_registry.py` (multi-backend registry)
- `agents/teams/product_team/TEAM_PACK.md` (reference pack)

---

## Phase 9 Scope Decision

Replay scope: handoff-level + tool-level only. Full LLM-call replay (replaying the language model deterministically) is **out of scope** — captured as a future-phase item. Rationale: Phase 1 tracer (`trace_checkpoints`) was never landed; tool_audit + handoff_audit give enough fidelity to verify routing + tool sequence determinism across pack version changes, which is the spec §9 acceptance criterion.

MCPProducer scope: stdio transport + bearer-token gate + `wiki_search` tool + `wiki://` resource. This is the minimum that satisfies spec §9 acceptance ("bearer auth round-trip works; wiki:// resource readable"). **Streamable HTTP transport** + scope-based authorization (per-call scope claims) deferred to a future hardening phase — public expose is not a Phase 9 requirement; Claude Code uses stdio.

---

## Codex log

**Pre-phase pass (2026-04-30): CHANGES-NEEDED → patched inline.**

Blockers fixed in this revision:
- **B-1 (MCPProducer §9 acceptance):** Task 9 now registers `wiki://` resource via FastMCP, adds bearer auth round-trip test, validates token presentation. Streamable HTTP + scope deferred to future phase (documented in scope decision).
- **B-2 (tool_audit not wired into runtime):** Task 5 now passes `session_id` through `handle_team_message` and calls `record_tool_call` after every non-delegate `execute_tool`. Task 6 schema unchanged; Task 7 replay updated to filter handoffs by session_id (requires schema bump — see below).
- **B-3 (hop counter not propagated):** Task 5 uses `parent_handoff.next_hop(target)` to build child Handoff so hop_count chains. New test `test_hop_limit_aborts` added.

Concerns addressed:
- **C-1 (replay session scoping):** Task 6 extended to add `session_id` column to `handoff_audit` (additive ALTER) + Task 7 filters by it.
- **C-2 (trust_boundary back-compat):** Task 1 adds pydantic `field_validator` mapping legacy bool True → `"legacy:phase-8"` and False/None → None.
- **C-3 (MCP stdio concurrent _call):** Task 8 adds `asyncio.Lock` in `__init__`, acquired in `_call`.
- **C-4 (max_parallel_members validate):** Task 4 adds validator `>=1`. Task 5 acknowledges serial-only semantics in docstring.
- **C-5 (test coverage shallow):** Task 5 adds nested-delegation test, hop-limit test, Trifecta-propagation test, non-delegate tool interleaving + tool_audit assertion.

**Re-validation pass (2026-04-30): residuals patched.**
- R-1: Task 5 router now constructed with `session_id=session_id` from start (no Task-6 reconciliation needed).
- R-2 + B-1 follow-up: bearer wired into MCP request path via `verify_bearer(token)` MCP tool — clients call after `initialize` for round-trip verification. End-to-end test added (`test_verify_bearer_tool_round_trip`).
- R-3: Task 4 verification command now runs `test_team_policy_rejects_zero_max_parallel`.
- R-4: termination test import path corrected to `from conexus.tests....` (not `src.conexus.tests....`).
- C-5 follow-up: standalone successful nested-delegation test added (`test_nested_delegation_success`) — verifies hop_count chain `0 → 1` and three-agent ana→researcher→pm route.

---

### Task 1: Replace `trust_boundary_cleared: bool` with reason string + audit hook (T-031)

**Files:**
- Modify: `src/conexus/core/team/handoff.py`
- Modify: `src/conexus/core/trifecta/guard.py`
- Modify: `src/conexus/core/team/handoff_router.py:53-56` (audit row write)
- Modify: `src/conexus/core/memory/handoff_audit.py:38` (column write)
- Test: `src/conexus/tests/test_framework_trust_clear.py` (NEW)

- [ ] **Step 1: Write the failing test**

```python
# src/conexus/tests/test_framework_trust_clear.py
"""Trust-boundary clear must be a logged operator action with reason string."""
from __future__ import annotations
import sqlite3
import pytest
from conexus.core.team.handoff import Handoff
from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation
from conexus.core.trifecta.tags import DataClass


def _h(**kw):
    base = dict(from_agent="a", to_agent="b", payload={})
    base.update(kw)
    return Handoff(**base)


def test_handoff_trust_cleared_is_optional_string():
    h = _h(trust_boundary_cleared="approved-by-leandro-2026-04-30")
    assert h.trust_boundary_cleared == "approved-by-leandro-2026-04-30"


def test_handoff_trust_cleared_default_none():
    h = _h()
    assert h.trust_boundary_cleared is None


def test_guard_from_handoff_passes_reason():
    h = _h(
        tags={DataClass.untrusted_read, DataClass.private_read},
        trust_boundary_cleared="manual-approval-123",
    )
    g = TrifectaGuard.from_handoff({"send_email": "external_write"}, h)
    g.check_and_record("send_email")  # must not raise — trust cleared


def test_guard_no_clear_still_blocks():
    h = _h(tags={DataClass.untrusted_read, DataClass.private_read})
    g = TrifectaGuard.from_handoff({"send_email": "external_write"}, h)
    with pytest.raises(TrifectaViolation):
        g.check_and_record("send_email")


def test_clear_boundary_method_records_reason():
    g = TrifectaGuard({"send_email": "external_write"})
    g._taint.add(DataClass.untrusted_read)
    g._taint.add(DataClass.private_read)
    g.clear_boundary("operator-override-ticket-42")
    assert g._trust_cleared == "operator-override-ticket-42"
    g.check_and_record("send_email")  # no raise


def test_audit_writes_trust_cleared_truthy_when_reason_set(tmp_path):
    from conexus.core.memory.handoff_audit import init_handoff_audit, record_handoff
    db = tmp_path / "audit.db"
    conn = sqlite3.connect(db)
    init_handoff_audit(conn)
    h = _h(trust_boundary_cleared="reason-x")
    record_handoff(conn, h, "routed")
    row = conn.execute("SELECT trust_cleared FROM handoff_audit").fetchone()
    assert row[0] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src/conexus/tests/test_framework_trust_clear.py -v`
Expected: 5 FAIL — string assignment to bool field rejected by pydantic, no `clear_boundary` method.

- [ ] **Step 3: Update Handoff model with back-compat validator**

```python
# src/conexus/core/team/handoff.py — add field_validator import + change field
from pydantic import BaseModel, Field, ConfigDict, field_validator

class Handoff(BaseModel):
    # ... other fields unchanged ...
    trust_boundary_cleared: str | None = None

    @field_validator("trust_boundary_cleared", mode="before")
    @classmethod
    def _coerce_legacy_bool(cls, v):
        """Phase 8 persisted bool True/False; replay must accept both."""
        if v is True:
            return "legacy:phase-8"
        if v is False:
            return None
        return v
```

Add round-trip test:

```python
# append to src/conexus/tests/test_framework_trust_clear.py
def test_handoff_legacy_bool_true_coerced_to_sentinel():
    """Replay must accept Phase 8 envelopes with bool True."""
    h = Handoff.model_validate_json(
        '{"schema_version":"1","from_agent":"a","to_agent":"b",'
        '"trust_boundary_cleared":true,"tags":[]}'
    )
    assert h.trust_boundary_cleared == "legacy:phase-8"


def test_handoff_legacy_bool_false_coerced_to_none():
    h = Handoff.model_validate_json(
        '{"schema_version":"1","from_agent":"a","to_agent":"b",'
        '"trust_boundary_cleared":false,"tags":[]}'
    )
    assert h.trust_boundary_cleared is None
```

- [ ] **Step 4: Update TrifectaGuard**

```python
# src/conexus/core/trifecta/guard.py — replace __init__ and add clear_boundary
    def __init__(
        self,
        tool_tags: dict[str, str],
        *,
        trust_boundary_cleared: str | None = None,
        seed_taint: set[DataClass] | None = None,
    ) -> None:
        self._tool_tags: dict[str, DataClass] = {}
        for name, tag in tool_tags.items():
            try:
                self._tool_tags[name] = DataClass(tag)
            except ValueError:
                pass
        self._trust_cleared: str | None = trust_boundary_cleared
        self._taint: set[DataClass] = set(seed_taint) if seed_taint else set()

    def clear_boundary(self, reason: str) -> None:
        """Operator-level trust-boundary clear. Reason is required; logged by caller."""
        if not reason or not reason.strip():
            raise ValueError("clear_boundary requires non-empty reason")
        self._trust_cleared = reason
```

Update the trust-cleared check (was `not self._trust_cleared` for bool; now must accept None as falsy):

```python
        if (
            tag == DataClass.external_write
            and self._trust_cleared is None
            and DataClass.untrusted_read in self._taint
            and DataClass.private_read in self._taint
        ):
```

- [ ] **Step 5: Update audit row write to coerce reason to bool int**

```python
# src/conexus/core/memory/handoff_audit.py — line 38 inside record_handoff
            int(h.trust_boundary_cleared is not None),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest src/conexus/tests/test_framework_trust_clear.py -v`
Expected: 5 PASS

- [ ] **Step 7: Run regression on existing trifecta + team tests**

Run: `uv run pytest src/conexus/tests/test_framework_trifecta.py src/conexus/tests/test_framework_trifecta_integration.py src/conexus/tests/test_framework_team_trifecta.py src/conexus/tests/test_framework_team_integration.py src/conexus/tests/test_framework_handoff.py -v`
Expected: ALL PASS. Existing tests passing `trust_boundary_cleared=True` keep working via the legacy-bool validator. Update them only if a test asserts the type explicitly.

- [ ] **Step 8: Commit**

```bash
git add src/conexus/core/team/handoff.py src/conexus/core/trifecta/guard.py src/conexus/core/memory/handoff_audit.py src/conexus/tests/test_framework_trust_clear.py
git commit -m "feat(phase-9): trust_boundary_cleared becomes reason str + clear_boundary method (T-031)"
```

---

### Task 2: `delegate_to_<agent>` LLM tool schema + Handoff builder (T-028, foundation)

**Files:**
- Create: `src/conexus/core/team/delegate_tool.py`
- Test: `src/conexus/tests/test_framework_delegate_tool.py` (NEW)

- [ ] **Step 1: Write the failing test**

```python
# src/conexus/tests/test_framework_delegate_tool.py
"""delegate_to_<agent> LLM tool schema generation + arg parsing."""
from __future__ import annotations
import pytest
from conexus.core.team.delegate_tool import (
    build_delegate_schemas,
    parse_delegate_call,
    DELEGATE_PREFIX,
)
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry


@pytest.fixture
def team(tmp_path):
    p = tmp_path / "TEAM_PACK.md"
    p.write_text(
        "---\n"
        "name: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, pm, researcher]\n"
        "edges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.4, pm: 0.3, researcher: 0.3}}\n"
        "---\n"
    )
    doc = TeamLoader({"ana", "pm", "researcher"}).load(str(p))
    return TeamRegistry(doc)


def test_build_delegate_schemas_one_per_member_minus_self(team):
    schemas = build_delegate_schemas(team, current_agent="ana")
    names = {s["function"]["name"] for s in schemas}
    assert names == {"delegate_to_pm", "delegate_to_researcher"}


def test_schema_has_required_payload_field(team):
    [s] = [s for s in build_delegate_schemas(team, "ana") if s["function"]["name"] == "delegate_to_pm"]
    params = s["function"]["parameters"]
    assert params["properties"]["task"]["type"] == "object"
    assert "task" in params["required"]


def test_parse_delegate_call_returns_target_and_payload():
    target, payload, opts = parse_delegate_call(
        f"{DELEGATE_PREFIX}pm",
        {"task": {"goal": "review design doc"}},
    )
    assert target == "pm"
    assert payload == {"task": {"goal": "review design doc"}}
    assert opts == {}


def test_parse_delegate_call_extracts_optional_overrides():
    _, _, opts = parse_delegate_call(
        f"{DELEGATE_PREFIX}pm",
        {"task": {"x": 1}, "context_mode": "full", "return_on": "DONE"},
    )
    assert opts == {"context_mode": "full", "return_on": "DONE"}


def test_parse_delegate_call_rejects_non_delegate_name():
    with pytest.raises(ValueError):
        parse_delegate_call("send_email", {})


def test_parse_delegate_call_rejects_unknown_context_mode():
    with pytest.raises(ValueError):
        parse_delegate_call(
            f"{DELEGATE_PREFIX}pm",
            {"task": {}, "context_mode": "bogus"},
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/conexus/tests/test_framework_delegate_tool.py -v`
Expected: ALL FAIL — module does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# src/conexus/core/team/delegate_tool.py
"""Builds the delegate_to_<agent> LLM tool schema for a team registry.

The agent loop sees these schemas alongside the agent's own tools. When the LLM
emits a tool call whose name starts with `delegate_to_`, the loop builds a
Handoff and yields control to the named sibling agent.
"""
from __future__ import annotations
from typing import Any
from conexus.core.team.team_registry import TeamRegistry

DELEGATE_PREFIX = "delegate_to_"
_VALID_MODES = ("full", "last_message", "summary")


def build_delegate_schemas(registry: TeamRegistry, current_agent: str) -> list[dict]:
    schemas: list[dict] = []
    for member in registry.members:
        if member == current_agent:
            continue
        schemas.append({
            "type": "function",
            "function": {
                "name": f"{DELEGATE_PREFIX}{member}",
                "description": f"Delegate sub-task to teammate '{member}'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "object",
                            "description": "Free-form payload describing the sub-task.",
                        },
                        "context_mode": {
                            "type": "string",
                            "enum": list(_VALID_MODES),
                            "description": "How much transcript to forward (default: summary).",
                        },
                        "return_on": {
                            "type": "string",
                            "description": "If set, target agent's reply containing this text returns control immediately.",
                        },
                    },
                    "required": ["task"],
                },
            },
        })
    return schemas


def parse_delegate_call(
    tool_name: str,
    args: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Returns (target_agent, payload, optional_overrides).

    Raises ValueError on malformed input.
    """
    if not tool_name.startswith(DELEGATE_PREFIX):
        raise ValueError(f"not a delegate call: {tool_name}")
    target = tool_name[len(DELEGATE_PREFIX):]
    if not target:
        raise ValueError("delegate target empty")
    if "task" not in args:
        raise ValueError("delegate call missing required 'task' field")
    payload = {"task": args["task"]}
    opts: dict[str, Any] = {}
    if "context_mode" in args:
        if args["context_mode"] not in _VALID_MODES:
            raise ValueError(f"invalid context_mode: {args['context_mode']}")
        opts["context_mode"] = args["context_mode"]
    if "return_on" in args:
        opts["return_on"] = str(args["return_on"])
    return target, payload, opts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest src/conexus/tests/test_framework_delegate_tool.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/conexus/core/team/delegate_tool.py src/conexus/tests/test_framework_delegate_tool.py
git commit -m "feat(phase-9): delegate_to_<agent> tool schema + arg parser (T-028 part 1)"
```

---

### Task 3: Transcript trimming for context_mode (T-029, foundation)

**Files:**
- Create: `src/conexus/core/team/transcript.py`
- Test: `src/conexus/tests/test_framework_transcript.py` (NEW)

- [ ] **Step 1: Write the failing test**

```python
# src/conexus/tests/test_framework_transcript.py
"""transcript trim modes: full | last_message | summary."""
from __future__ import annotations
import pytest
from conexus.core.team.transcript import trim_transcript


def _msgs():
    return [
        {"role": "system", "content": "You are ana."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "research X"},
        {"role": "assistant", "content": "found X"},
    ]


def test_full_returns_all():
    out = trim_transcript(_msgs(), "full")
    assert len(out) == 5
    assert out is not _msgs()  # must be a copy


def test_last_message_returns_only_last_non_system():
    out = trim_transcript(_msgs(), "last_message")
    assert len(out) == 1
    assert out[0]["role"] == "assistant"
    assert out[0]["content"] == "found X"


def test_summary_returns_compact_marker():
    out = trim_transcript(_msgs(), "summary")
    assert len(out) == 1
    assert out[0]["role"] == "system"
    assert "transcript summary" in out[0]["content"].lower()
    assert "5 prior message" in out[0]["content"]


def test_empty_input():
    assert trim_transcript([], "full") == []
    assert trim_transcript([], "last_message") == []
    out = trim_transcript([], "summary")
    assert len(out) == 1


def test_invalid_mode():
    with pytest.raises(ValueError):
        trim_transcript(_msgs(), "bogus")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/conexus/tests/test_framework_transcript.py -v`
Expected: 5 FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# src/conexus/core/team/transcript.py
"""Per-edge transcript trimming for cross-agent handoffs."""
from __future__ import annotations


def trim_transcript(messages: list[dict], mode: str) -> list[dict]:
    """Return a trimmed copy of `messages` per `context_mode`.

    Modes:
      full          — full copy.
      last_message  — only the last non-system message.
      summary       — single system message marking N prior turns.
    """
    if mode == "full":
        return list(messages)
    if mode == "last_message":
        for m in reversed(messages):
            if m.get("role") != "system":
                return [dict(m)]
        return []
    if mode == "summary":
        n = len(messages)
        return [{
            "role": "system",
            "content": f"Transcript summary: {n} prior message(s) elided by handoff context_mode=summary.",
        }]
    raise ValueError(f"invalid context_mode: {mode}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest src/conexus/tests/test_framework_transcript.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/conexus/core/team/transcript.py src/conexus/tests/test_framework_transcript.py
git commit -m "feat(phase-9): trim_transcript for full|last_message|summary modes (T-029 part 1)"
```

---

### Task 4: max_parallel_members policy field (T-030, additive)

**Files:**
- Modify: `src/conexus/core/team/team_pack.py`
- Test: extend `src/conexus/tests/test_framework_team_pack.py` if it exists, else add to `src/conexus/tests/test_framework_team_loop_termination.py`.

- [ ] **Step 1: Write the failing test**

```python
# add to src/conexus/tests/test_framework_team_loop_termination.py (NEW or extend)
"""max_parallel_members + termination_text loop wiring."""
from __future__ import annotations
from conexus.core.team.team_pack import TeamPolicy


def test_team_policy_default_max_parallel_members_is_one():
    p = TeamPolicy()
    assert p.max_parallel_members == 1


def test_team_policy_accepts_override():
    p = TeamPolicy(max_parallel_members=3)
    assert p.max_parallel_members == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/conexus/tests/test_framework_team_loop_termination.py -v`
Expected: FAIL — `max_parallel_members` is not a TeamPolicy field.

- [ ] **Step 3: Add field with validator**

```python
# src/conexus/core/team/team_pack.py — class TeamPolicy
from pydantic import BaseModel, Field, field_validator

class TeamPolicy(BaseModel):
    trifecta_enforcement: Literal["strict", "warn", "off"] = "strict"
    max_hops: int = 5
    max_turns: int = 20
    max_parallel_members: int = 1
    termination_text: str = "DONE"

    @field_validator("max_parallel_members")
    @classmethod
    def _check_at_least_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_parallel_members must be >= 1")
        return v
```

Add validator test:

```python
import pytest
def test_team_policy_rejects_zero_max_parallel():
    with pytest.raises(Exception):  # pydantic ValidationError
        TeamPolicy(max_parallel_members=0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest src/conexus/tests/test_framework_team_loop_termination.py::test_team_policy_default_max_parallel_members_is_one src/conexus/tests/test_framework_team_loop_termination.py::test_team_policy_accepts_override src/conexus/tests/test_framework_team_loop_termination.py::test_team_policy_rejects_zero_max_parallel -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conexus/core/team/team_pack.py src/conexus/tests/test_framework_team_loop_termination.py
git commit -m "feat(phase-9): add max_parallel_members to TeamPolicy (T-030 part 1)"
```

---

### Task 5: Wire delegate + context_mode + return_on + termination_text + tool_audit + hop-count into agent loop (T-028 + T-029 + T-030 finish; addresses codex B-2 + B-3 + C-5)

**Files:**
- Modify: `src/conexus/core/agent_handler.py` (new public fn `handle_team_message`)
- Test: `src/conexus/tests/test_framework_team_loop.py` (NEW)
- Test: `src/conexus/tests/test_framework_team_loop_termination.py` (extend)

> **Implementer notes:**
> 1. Ships behind a fake-LLM driver — we do NOT call real LLMs. The test rigs `TrackedLLM.acall` to a deterministic stub returning scripted responses.
> 2. **Serial-only delegation** for Phase 9: `policy.max_parallel_members >= 1` is validated, but the loop processes one delegation per parent turn (true parallel deferred). Documented in the function docstring.
> 3. **Hop-count chain (codex B-3):** Each child Handoff is built via `parent_handoff.next_hop(target)` so `hop_count` increments. Initial root handoff starts at `hop_count=0`; `next_hop()` raises if `hop_count + 1 > max_hops`. The starter agent has no parent — its first delegation creates a fresh root Handoff at `hop_count=0`.
> 4. **Tool audit wiring (codex B-2):** `handle_team_message` accepts `session_id: str` (defaults to a random UUID per call); every non-delegate `execute_tool(...)` is followed by `record_tool_call(conn, session_id, agent, tool, args, result, outcome)` where outcome is `"ok"` or `"trifecta_blocked"`.

- [ ] **Step 1: Write the failing integration test**

```python
# src/conexus/tests/test_framework_team_loop.py
"""End-to-end multi-agent delegate cycle with stubbed LLMs."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
import pytest
from conexus.core.agent_handler import AgentHandlerConfig, handle_team_message
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.budget.cap_checker import CapChecker
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry


def _msg_tool(call_id: str, fn_name: str, fn_args_json: str):
    return SimpleNamespace(
        tool_calls=[SimpleNamespace(
            id=call_id,
            function=SimpleNamespace(name=fn_name, arguments=fn_args_json),
        )],
        content=None,
    )


def _msg_text(text: str):
    return SimpleNamespace(tool_calls=None, content=text)


@dataclass
class FakeLLM:
    """Returns the next scripted message from `script` per call."""
    script: list[Any]
    config: Any = field(default_factory=lambda: SimpleNamespace(temperature=0.0))
    _i: int = 0

    async def acall(self, **kwargs):
        m = self.script[self._i]
        self._i += 1
        resp = SimpleNamespace(choices=[SimpleNamespace(message=m)])
        return resp, "fake-model"


@pytest.fixture
def team(tmp_path):
    p = tmp_path / "TEAM_PACK.md"
    p.write_text(
        "---\n"
        "name: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, researcher]\n"
        "edges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, researcher: 0.5}}\n"
        "policy: {max_hops: 5, max_turns: 5, termination_text: DONE}\n"
        "---\n"
    )
    doc = TeamLoader({"ana", "researcher"}).load(str(p))
    return TeamRegistry(doc)


@pytest.mark.asyncio
async def test_delegate_yields_then_returns(tmp_path, team):
    db = tmp_path / "c.db"
    store = SqliteStore(str(db))

    async def exec_tool_ana(name, args):
        return "{}"

    async def exec_tool_research(name, args):
        return '"web result: X is foo"'

    ana_cfg = AgentHandlerConfig(
        name="ana",
        llm=FakeLLM(script=[
            _msg_tool("c1", "delegate_to_researcher", '{"task": {"goal": "look up X"}}'),
            _msg_text("Final answer based on research."),
        ]),
        tools_schema=[],
        execute_tool=exec_tool_ana,
        system_prompt="you are ana",
        tool_tags=None,
    )
    researcher_cfg = AgentHandlerConfig(
        name="researcher",
        llm=FakeLLM(script=[
            _msg_text("X is foo."),
        ]),
        tools_schema=[],
        execute_tool=exec_tool_research,
        system_prompt="you are researcher",
        tool_tags=None,
    )

    cap_checker = CapChecker(store)
    reply = await handle_team_message(
        team=team,
        configs={"ana": ana_cfg, "researcher": researcher_cfg},
        store=store,
        cap_checker=cap_checker,
        body="please find X",
        session_id="sess-test-1",
    )
    assert reply == "Final answer based on research."


@pytest.mark.asyncio
async def test_return_on_short_circuits(tmp_path, team):
    db = tmp_path / "c.db"
    store = SqliteStore(str(db))

    async def exec_tool_any(name, args):
        return "{}"

    ana_cfg = AgentHandlerConfig(
        name="ana",
        llm=FakeLLM(script=[
            _msg_tool("c1", "delegate_to_researcher",
                      '{"task": {"goal": "x"}, "return_on": "RESULT_OK"}'),
            _msg_text("Done."),
        ]),
        tools_schema=[],
        execute_tool=exec_tool_any,
        system_prompt="ana",
        tool_tags=None,
    )
    researcher_cfg = AgentHandlerConfig(
        name="researcher",
        llm=FakeLLM(script=[
            _msg_text("RESULT_OK: foo"),
        ]),
        tools_schema=[],
        execute_tool=exec_tool_any,
        system_prompt="researcher",
        tool_tags=None,
    )

    cap_checker = CapChecker(store)
    reply = await handle_team_message(
        team=team, configs={"ana": ana_cfg, "researcher": researcher_cfg},
        store=store, cap_checker=cap_checker, body="x",
        session_id="sess-ret",
    )
    assert reply == "Done."


@pytest.mark.asyncio
async def test_nested_delegation_success(tmp_path):
    """ana → researcher → pm chain, all return naturally, hop_count chains."""
    pack = tmp_path / "TEAM_PACK.md"
    pack.write_text(
        "---\nname: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, researcher, pm]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.4, researcher: 0.3, pm: 0.3}}\n"
        "policy: {max_hops: 5, max_turns: 6, termination_text: DONE}\n---\n"
    )
    doc = TeamLoader({"ana", "researcher", "pm"}).load(str(pack))
    team = TeamRegistry(doc)
    store = SqliteStore(str(tmp_path / "c.db"))

    async def exec_tool(name, args):
        return "{}"

    ana = AgentHandlerConfig(
        name="ana", llm=FakeLLM(script=[
            _msg_tool("c1", "delegate_to_researcher", '{"task": {"q": "x"}}'),
            _msg_text("Final ana DONE."),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="ana", tool_tags=None,
    )
    res = AgentHandlerConfig(
        name="researcher", llm=FakeLLM(script=[
            _msg_tool("c2", "delegate_to_pm", '{"task": {"r": "y"}}'),
            _msg_text("researcher reply"),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="researcher", tool_tags=None,
    )
    pm = AgentHandlerConfig(
        name="pm", llm=FakeLLM(script=[
            _msg_text("pm reply"),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="pm", tool_tags=None,
    )
    cap_checker = CapChecker(store)
    reply = await handle_team_message(
        team=team, configs={"ana": ana, "researcher": res, "pm": pm},
        store=store, cap_checker=cap_checker, body="go",
        session_id="sess-nested",
    )
    assert reply == "Final ana DONE."
    # Verify both handoffs recorded with chained hop_counts
    rows = store.conn.execute(
        "SELECT from_agent, to_agent, hop_count FROM handoff_audit WHERE session_id=? ORDER BY id",
        ("sess-nested",),
    ).fetchall()
    assert rows == [("ana", "researcher", 0), ("researcher", "pm", 1)]


@pytest.mark.asyncio
async def test_hop_limit_aborts(tmp_path):
    """Nested delegation exceeding policy.max_hops must surface ValueError as a tool error."""
    pack = tmp_path / "TEAM_PACK.md"
    pack.write_text(
        "---\nname: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, researcher]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, researcher: 0.5}}\n"
        "policy: {max_hops: 1, max_turns: 6, termination_text: DONE}\n---\n"
    )
    doc = TeamLoader({"ana", "researcher"}).load(str(pack))
    team = TeamRegistry(doc)
    store = SqliteStore(str(tmp_path / "c.db"))

    async def exec_tool(name, args):
        return "{}"

    # Ana delegates → researcher delegates back to ana → must abort (hop=2 > max_hops=1)
    ana_cfg = AgentHandlerConfig(
        name="ana", llm=FakeLLM(script=[
            _msg_tool("c1", "delegate_to_researcher", '{"task": {"x": 1}}'),
            _msg_text("Aborted DONE."),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="ana", tool_tags=None,
    )
    res_cfg = AgentHandlerConfig(
        name="researcher", llm=FakeLLM(script=[
            _msg_tool("c2", "delegate_to_ana", '{"task": {"y": 2}}'),
            _msg_text("RESULT done"),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="researcher", tool_tags=None,
    )
    cap_checker = CapChecker(store)
    reply = await handle_team_message(
        team=team, configs={"ana": ana_cfg, "researcher": res_cfg},
        store=store, cap_checker=cap_checker, body="go",
        session_id="sess-hop",
    )
    assert reply == "Aborted DONE."  # ana saw a hop-limit error, ended naturally


@pytest.mark.asyncio
async def test_tool_audit_records_non_delegate_calls(tmp_path, team):
    """Every non-delegate execute_tool must produce a tool_audit row."""
    import sqlite3
    db = tmp_path / "c.db"
    store = SqliteStore(str(db))

    async def exec_tool(name, args):
        return '"foo"'

    ana_cfg = AgentHandlerConfig(
        name="ana", llm=FakeLLM(script=[
            _msg_tool("c1", "search", '{"q": "weather"}'),
            _msg_text("All good DONE."),
        ]),
        tools_schema=[{"type": "function", "function": {"name": "search", "parameters": {"type": "object"}}}],
        execute_tool=exec_tool,
        system_prompt="ana", tool_tags=None,
    )
    res_cfg = AgentHandlerConfig(
        name="researcher", llm=FakeLLM(script=[]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="researcher", tool_tags=None,
    )
    cap_checker = CapChecker(store)
    await handle_team_message(
        team=team, configs={"ana": ana_cfg, "researcher": res_cfg},
        store=store, cap_checker=cap_checker, body="go",
        session_id="sess-audit",
    )
    rows = store.conn.execute(
        "SELECT agent, tool, outcome FROM tool_audit WHERE session_id=?",
        ("sess-audit",),
    ).fetchall()
    assert ("ana", "search", "ok") in rows


@pytest.mark.asyncio
async def test_trifecta_propagates_through_handoff(tmp_path):
    """Child agent's TrifectaGuard must inherit parent's taint via Handoff.tags."""
    from conexus.core.trifecta.tags import DataClass
    pack = tmp_path / "TEAM_PACK.md"
    pack.write_text(
        "---\nname: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, pm]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, pm: 0.5}}\n---\n"
    )
    doc = TeamLoader({"ana", "pm"}).load(str(pack))
    team = TeamRegistry(doc)
    store = SqliteStore(str(tmp_path / "c.db"))

    async def exec_tool(name, args):
        return '"x"'

    # Ana calls untrusted + private read tools first → her TrifectaGuard
    # accumulates {untrusted_read, private_read} in _taint. When she delegates
    # to PM, the team loop seeds the child Handoff.tags with parent guard's
    # current _taint. PM's from_handoff inherits that taint, then send_email
    # (external_write) trips the trifecta block.
    ana_cfg = AgentHandlerConfig(
        name="ana", llm=FakeLLM(script=[
            _msg_tool("c1", "fetch_url", '{"url": "x"}'),     # untrusted_read auto-tag
            _msg_tool("c2", "read_secrets", '{"k": "y"}'),    # private_read auto-tag
            _msg_tool("c3", "delegate_to_pm", '{"task": {"x": 1}}'),
            _msg_text("Done DONE."),
        ]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="ana",
        tool_tags={
            "fetch_url": "untrusted_read",
            "read_secrets": "private_read",
            "send_email": "external_write",
        },
    )
    pm_cfg = AgentHandlerConfig(
        name="pm", llm=FakeLLM(script=[
            _msg_tool("c2", "send_email", '{"to": "x"}'),
            _msg_text("RESULT (blocked)"),
        ]),
        tools_schema=[{"type": "function", "function": {"name": "send_email", "parameters": {"type": "object"}}}],
        execute_tool=exec_tool,
        system_prompt="pm",
        tool_tags={"send_email": "external_write"},
    )
    cap_checker = CapChecker(store)
    await handle_team_message(
        team=team, configs={"ana": ana_cfg, "pm": pm_cfg},
        store=store, cap_checker=cap_checker, body="go",
        session_id="sess-tri",
    )
    rows = store.conn.execute(
        "SELECT agent, tool, outcome FROM tool_audit WHERE session_id=?",
        ("sess-tri",),
    ).fetchall()
    assert ("pm", "send_email", "trifecta_blocked") in rows
```

> **Cross-agent taint propagation rule:** When the parent's frame has a TrifectaGuard, the team loop seeds the child Handoff's `tags` with `parent_guard._taint` automatically. No LLM-visible parameter; it is an internal invariant. Add an accessor on TrifectaGuard (`tainted_with -> set[DataClass]`) to avoid touching `_taint` from outside the class.

Add accessor:

```python
# src/conexus/core/trifecta/guard.py — add method
    def tainted_with(self) -> set[DataClass]:
        """Snapshot of current taint set. Used by team loop for cross-agent seeding."""
        return set(self._taint)
```

- [ ] **Step 2: Write the termination_text test**

```python
# add to src/conexus/tests/test_framework_team_loop_termination.py
import asyncio
import pytest
from conexus.core.agent_handler import handle_team_message  # noqa: F401
# (use same FakeLLM from test_framework_team_loop.py via import)


@pytest.mark.asyncio
async def test_termination_text_in_reply_ends_loop(tmp_path):
    """If member emits text containing policy.termination_text, loop returns it as final."""
    # Skipped scaffold: fully fleshed in implementation step.
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest src/conexus/tests/test_framework_team_loop.py -v`
Expected: FAIL — `handle_team_message` does not exist.

- [ ] **Step 4: Implement handle_team_message + delegate dispatch in agent_handler**

```python
# src/conexus/core/agent_handler.py — append at bottom
import uuid

async def handle_team_message(
    *,
    team,                       # TeamRegistry
    configs: dict[str, AgentHandlerConfig],
    store: SqliteStore,
    cap_checker: CapChecker,
    body: str,
    session_id: str | None = None,
    progress=None,
) -> str:
    """Run the team loop: route LLM-emitted delegate_to_<agent> calls between members.

    Starts at team.manager (or first member if no manager). Each `delegate_to_<X>`
    tool call builds a Handoff, routes it via HandoffRouter, swaps to target's
    config (with trimmed transcript + incoming_handoff), and returns control on
    either a natural reply (no tool call) OR a reply containing
    handoff.return_on (when set) OR policy.termination_text.

    Hop guard: each child Handoff is built via parent.next_hop(target), which
    raises ValueError when hop_count + 1 > max_hops. The error is caught and
    surfaced to the parent LLM as a tool error.

    Parallel guard: policy.max_parallel_members validated >=1; Phase 9 enforces
    serial-only (one delegation per parent turn).

    Audit: every non-delegate execute_tool result is recorded via
    record_tool_call(conn, session_id=...). session_id defaults to a per-call
    UUID4 if not supplied.

    Cross-agent Trifecta: child's TrifectaGuard inherits parent guard's
    tainted_with() set via Handoff.tags.
    """
    from conexus.core.memory.tool_audit import record_tool_call
    from conexus.core.team.delegate_tool import (
        DELEGATE_PREFIX,
        build_delegate_schemas,
        parse_delegate_call,
    )
    from conexus.core.team.handoff import Handoff
    from conexus.core.team.handoff_router import HandoffRouter
    from conexus.core.team.transcript import trim_transcript
    from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation
    from conexus.core.trifecta.tags import DataClass

    if session_id is None:
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
    audit_conn = store.conn if hasattr(store, "conn") else None

    starter = team.manager or team.members[0]
    if starter not in configs:
        raise ValueError(f"no AgentHandlerConfig for starter '{starter}'")

    router = HandoffRouter(team, conn=audit_conn, session_id=session_id)
    policy = team.policy
    termination_text = policy.termination_text

    # Stack frame: (agent_name, messages, return_on, max_turns_remaining, last_handoff)
    @dataclass
    class _Frame:
        name: str
        messages: list[dict]
        return_on: str | None
        turns_left: int
        guard: object | None
        execute_tool: Any
        is_async_tool: bool
        cfg: AgentHandlerConfig
        last_handoff: Handoff | None  # parent handoff into this frame; None for root

    def _make_frame(name: str, messages: list[dict], handoff: Handoff | None,
                    return_on: str | None) -> _Frame:
        cfg = configs[name]
        if cfg.tool_tags is None:
            g = None
        elif handoff is not None:
            g = TrifectaGuard.from_handoff(cfg.tool_tags, handoff)
        else:
            g = TrifectaGuard(cfg.tool_tags)
        return _Frame(
            name=name,
            messages=messages,
            return_on=return_on,
            turns_left=cfg.max_turns,
            guard=g,
            execute_tool=cfg.execute_tool,
            is_async_tool=inspect.iscoroutinefunction(cfg.execute_tool),
            cfg=cfg,
            last_handoff=handoff,
        )

    # Initial frame for starter agent
    now_brt = datetime.now(_BRT)
    starter_cfg = configs[starter]
    history = store.chat_recent(starter, limit=10)
    context_lines = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    sys_prompt = (
        starter_cfg.system_prompt
        + f"\n\nData/hora atual (BRT): {now_brt.strftime('%Y-%m-%d %H:%M %Z')}"
    )
    initial_msgs: list[dict] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"Histórico recente:\n{context_lines}\n\nLeandro agora: {body}"},
    ]
    store.chat_append(starter, "user", body)

    stack: list[_Frame] = [_make_frame(starter, initial_msgs, None, None)]

    last_reply: str | None = None

    while stack:
        frame = stack[-1]
        if frame.turns_left <= 0:
            stack.pop()
            continue
        frame.turns_left -= 1

        # Augment tools_schema with delegate_to_<other>
        delegate_schemas = build_delegate_schemas(team, frame.name)
        all_tools = list(frame.cfg.tools_schema) + delegate_schemas

        resp, _model = await frame.cfg.llm.acall(
            messages=frame.messages,
            tools=all_tools,
            tool_choice="auto",
            temperature=frame.cfg.llm.config.temperature,
        )
        msg = resp.choices[0].message
        tool_calls = (
            getattr(msg, "tool_calls", None)
            or (msg.get("tool_calls") if isinstance(msg, dict) else None)
        )
        text_content = (
            getattr(msg, "content", None)
            or (msg.get("content") if isinstance(msg, dict) else None)
        )

        if tool_calls:
            frame.messages.append(
                msg if isinstance(msg, dict) else msg.model_dump(exclude_unset=True)
            )
            for tc in tool_calls:
                fn_name = tc.function.name if hasattr(tc, "function") else tc["function"]["name"]
                fn_args_raw = (
                    tc.function.arguments if hasattr(tc, "function")
                    else tc["function"]["arguments"]
                )
                tc_id = tc.id if hasattr(tc, "id") else tc["id"]
                try:
                    fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                except json.JSONDecodeError:
                    fn_args = {}

                if fn_name.startswith(DELEGATE_PREFIX):
                    target, payload, opts = parse_delegate_call(fn_name, fn_args)
                    # Build child handoff via parent.next_hop() to chain hop_count.
                    # Auto-seed tags from parent guard's current taint (cross-agent Trifecta).
                    seed_tags: set[DataClass] = (
                        frame.guard.tainted_with() if frame.guard else set()
                    )
                    try:
                        if frame.last_handoff is not None:
                            h = frame.last_handoff.next_hop(target).model_copy(update={
                                "from_agent": frame.name,
                                "payload": payload,
                                "context_mode": opts.get("context_mode", "summary"),
                                "return_on": opts.get("return_on"),
                                "tags": seed_tags,
                            })
                        else:
                            h = Handoff(
                                from_agent=frame.name,
                                to_agent=target,
                                payload=payload,
                                context_mode=opts.get("context_mode", "summary"),
                                return_on=opts.get("return_on"),
                                max_hops=policy.max_hops,
                                hop_count=0,
                                tags=seed_tags,
                            )
                    except ValueError as exc:
                        # Hop limit hit — surface as tool error, parent continues.
                        frame.messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": json.dumps({"error": f"hop_limit: {exc}"}),
                        })
                        continue
                    try:
                        resolved = router.route(h)
                    except ValueError as exc:
                        frame.messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": json.dumps({"error": f"route_failed: {exc}"}),
                        })
                        continue
                    # Build child frame with trimmed transcript + payload as user msg
                    child_msgs = trim_transcript(frame.messages, h.context_mode)
                    if not any(m.get("role") == "system" for m in child_msgs):
                        child_msgs.insert(0, {
                            "role": "system",
                            "content": configs[resolved].system_prompt,
                        })
                    child_msgs.append({
                        "role": "user",
                        "content": f"Delegated by {frame.name}: {json.dumps(payload['task'])}",
                    })
                    # Acknowledge delegation in caller transcript
                    frame.messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps({"delegated_to": resolved}),
                    })
                    child = _make_frame(resolved, child_msgs, h, h.return_on)
                    stack.append(child)
                    break  # handle one delegation per LLM turn (max_parallel_members=1)
                else:
                    if frame.guard:
                        try:
                            frame.guard.check_and_record(fn_name)
                        except (TrifectaViolation, ValueError) as exc:
                            blocked = json.dumps({"error": f"TrifectaGuard: {exc}"})
                            frame.messages.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": blocked,
                            })
                            if audit_conn is not None:
                                record_tool_call(
                                    audit_conn,
                                    session_id=session_id,
                                    agent=frame.name,
                                    tool=fn_name,
                                    args=fn_args,
                                    result=blocked,
                                    outcome="trifecta_blocked",
                                )
                            continue
                    result = (
                        await frame.execute_tool(fn_name, fn_args)
                        if frame.is_async_tool
                        else frame.execute_tool(fn_name, fn_args)
                    )
                    frame.messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})
                    if audit_conn is not None:
                        record_tool_call(
                            audit_conn,
                            session_id=session_id,
                            agent=frame.name,
                            tool=fn_name,
                            args=fn_args,
                            result=result,
                            outcome="ok",
                        )
            continue

        # Plain text reply: pop frame, propagate result to caller (or return).
        reply = text_content or "Pronto."
        last_reply = reply

        # termination_text → end the whole loop with this reply
        if termination_text and termination_text in reply:
            store.chat_append(stack[0].name, "assistant", reply)
            return reply

        # return_on → pop only this frame, hand reply back to parent as tool result
        if frame.return_on and frame.return_on in reply:
            stack.pop()
            if stack:
                # Append synthetic tool result on parent's last delegated tool_call
                parent = stack[-1]
                parent.messages.append({
                    "role": "user",
                    "content": f"[returned from {frame.name}]: {reply}",
                })
            continue

        # Frame finished naturally
        stack.pop()
        if stack:
            parent = stack[-1]
            parent.messages.append({
                "role": "user",
                "content": f"[returned from {frame.name}]: {reply}",
            })

    final = last_reply or starter_cfg.fallback_msg
    store.chat_append(starter, "assistant", final)
    return final
```

- [ ] **Step 5: Flesh out the termination_text test**

```python
# src/conexus/tests/test_framework_team_loop_termination.py — append
import pytest
from conexus.tests.test_framework_team_loop import (  # type: ignore
    FakeLLM, _msg_tool, _msg_text, team as team_fixture,
)
from conexus.core.agent_handler import AgentHandlerConfig, handle_team_message
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.budget.cap_checker import CapChecker


@pytest.mark.asyncio
async def test_termination_text_ends_loop(tmp_path, team_fixture):
    store = SqliteStore(str(tmp_path / "c.db"))

    async def exec_tool(name, args):
        return "{}"

    ana_cfg = AgentHandlerConfig(
        name="ana", llm=FakeLLM(script=[_msg_text("All done DONE.")]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="ana", tool_tags=None,
    )
    res_cfg = AgentHandlerConfig(
        name="researcher", llm=FakeLLM(script=[]),
        tools_schema=[], execute_tool=exec_tool,
        system_prompt="researcher", tool_tags=None,
    )
    reply = await handle_team_message(
        team=team_fixture,
        configs={"ana": ana_cfg, "researcher": res_cfg},
        store=store,
        cap_checker=CapChecker(store),
        body="please go",
    )
    assert reply == "All done DONE."
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest src/conexus/tests/test_framework_team_loop.py src/conexus/tests/test_framework_team_loop_termination.py -v`
Expected: 2 + 3 PASS.

- [ ] **Step 7: Run regression**

Run: `uv run pytest src/conexus/tests/test_framework_handoff.py src/conexus/tests/test_framework_handoff_router.py src/conexus/tests/test_framework_team_integration.py -v`
Expected: ALL PASS.

- [ ] **Step 8: Commit**

```bash
git add src/conexus/core/agent_handler.py src/conexus/tests/test_framework_team_loop.py src/conexus/tests/test_framework_team_loop_termination.py
git commit -m "feat(phase-9): handle_team_message — delegate/context/return_on/termination wiring (T-028, T-029, T-030)"
```

---

### Task 6: tool_audit table + session_id column on handoff_audit + record_tool_call (T-032 foundation; addresses codex C-1)

**Files:**
- Create: `src/conexus/core/memory/tool_audit.py`
- Modify: `src/conexus/core/memory/handoff_audit.py` — add `session_id TEXT NOT NULL DEFAULT 'legacy'` column + accept session_id in `record_handoff`.
- Modify: `src/conexus/core/team/handoff_router.py` — accept optional `session_id`, pass through.
- Modify: `src/conexus/core/memory/sqlite_store.py` — call `init_tool_audit` from `init_db`.
- Test: `src/conexus/tests/test_framework_tool_audit.py` (NEW)
- Test: extend `src/conexus/tests/test_framework_handoff_router.py` for session_id propagation.

- [ ] **Step 1: Write the failing test**

```python
# src/conexus/tests/test_framework_tool_audit.py
"""tool_audit table + record_tool_call."""
from __future__ import annotations
import json
import sqlite3
from conexus.core.memory.tool_audit import init_tool_audit, record_tool_call


def test_init_creates_table(tmp_path):
    conn = sqlite3.connect(tmp_path / "a.db")
    init_tool_audit(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tool_audit)").fetchall()}
    assert {"id", "ts", "session_id", "agent", "tool", "args_json", "result", "outcome"} <= cols


def test_record_round_trip(tmp_path):
    conn = sqlite3.connect(tmp_path / "a.db")
    init_tool_audit(conn)
    record_tool_call(
        conn,
        session_id="sess-1",
        agent="ana",
        tool="search",
        args={"q": "weather"},
        result='"hot"',
        outcome="ok",
    )
    rows = conn.execute("SELECT session_id, agent, tool, args_json, result, outcome FROM tool_audit").fetchall()
    assert rows == [("sess-1", "ana", "search", json.dumps({"q": "weather"}), '"hot"', "ok")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/conexus/tests/test_framework_tool_audit.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write implementation**

```python
# src/conexus/core/memory/tool_audit.py
"""SQLite-backed audit log for tool calls (replay fidelity)."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_audit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  session_id  TEXT NOT NULL,
  agent       TEXT NOT NULL,
  tool        TEXT NOT NULL,
  args_json   TEXT NOT NULL,
  result      TEXT NOT NULL,
  outcome     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_audit_session ON tool_audit(session_id);
"""


def init_tool_audit(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def record_tool_call(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    agent: str,
    tool: str,
    args: dict[str, Any],
    result: str,
    outcome: str,
) -> None:
    conn.execute(
        "INSERT INTO tool_audit (ts, session_id, agent, tool, args_json, result, outcome) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            session_id, agent, tool,
            json.dumps(args, sort_keys=True),
            result, outcome,
        ),
    )
    conn.commit()
```

- [ ] **Step 4: Wire into SqliteStore.init_db + add session_id to handoff_audit**

```python
# src/conexus/core/memory/sqlite_store.py — inside init_db, after init_handoff_audit
        from conexus.core.memory.tool_audit import init_tool_audit
        init_tool_audit(self._conn)
```

Add session_id column (additive ALTER, idempotent):

```python
# src/conexus/core/memory/handoff_audit.py — replace SCHEMA + record_handoff
SCHEMA = """
CREATE TABLE IF NOT EXISTS handoff_audit (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL,
  session_id      TEXT NOT NULL DEFAULT 'legacy',
  from_agent      TEXT NOT NULL,
  to_agent        TEXT NOT NULL,
  hop_count       INTEGER NOT NULL,
  tags            TEXT NOT NULL,
  trust_cleared   INTEGER NOT NULL,
  payload_json    TEXT NOT NULL,
  outcome         TEXT NOT NULL
);
"""

def init_handoff_audit(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # Idempotent migration for existing DBs lacking session_id
    cols = {r[1] for r in conn.execute("PRAGMA table_info(handoff_audit)").fetchall()}
    if "session_id" not in cols:
        conn.execute("ALTER TABLE handoff_audit ADD COLUMN session_id TEXT NOT NULL DEFAULT 'legacy'")
    conn.commit()


def record_handoff(conn: sqlite3.Connection, h: Handoff, outcome: str,
                    *, session_id: str = "legacy") -> None:
    conn.execute(
        "INSERT INTO handoff_audit (ts, session_id, from_agent, to_agent, hop_count, "
        "tags, trust_cleared, payload_json, outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            session_id,
            h.from_agent,
            h.to_agent,
            h.hop_count,
            json.dumps(sorted(t.value for t in h.tags)),
            int(h.trust_boundary_cleared is not None),
            h.model_dump_json(),
            outcome,
        ),
    )
    conn.commit()
```

Update HandoffRouter:

```python
# src/conexus/core/team/handoff_router.py — extend ctor + audit
class HandoffRouter:
    def __init__(self, registry, conn=None, *, session_id: str = "legacy"):
        self._reg = registry
        self._conn = conn
        self._session_id = session_id

    def _audit(self, handoff, outcome):
        if self._conn is None:
            return
        record_handoff(self._conn, handoff, outcome, session_id=self._session_id)
```

Update `handle_team_message` to construct router with session_id:
```python
    router = HandoffRouter(team, conn=audit_conn, session_id=session_id)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest src/conexus/tests/test_framework_tool_audit.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/conexus/core/memory/tool_audit.py src/conexus/core/memory/sqlite_store.py src/conexus/tests/test_framework_tool_audit.py
git commit -m "feat(phase-9): tool_audit table + record_tool_call (T-032 part 1)"
```

---

### Task 7: Replay runner — replay_session() (T-032 finish)

**Files:**
- Create: `src/conexus/core/team/replay.py`
- Modify: `src/conexus/cli/__main__.py` — add `replay` subcommand.
- Test: `src/conexus/tests/test_framework_replay.py` (NEW)

- [ ] **Step 1: Write the failing test**

```python
# src/conexus/tests/test_framework_replay.py
"""Deterministic replay of frozen handoff_audit + tool_audit traces."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
import pytest
from conexus.core.memory.handoff_audit import init_handoff_audit, record_handoff
from conexus.core.memory.tool_audit import init_tool_audit, record_tool_call
from conexus.core.team.handoff import Handoff
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry
from conexus.core.team.replay import replay_session, ReplayMismatch


@pytest.fixture
def db_with_team(tmp_path):
    pack = tmp_path / "TEAM_PACK.md"
    pack.write_text(
        "---\n"
        "name: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, researcher]\n"
        "edges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, researcher: 0.5}}\n"
        "---\n"
    )
    db = tmp_path / "c.db"
    conn = sqlite3.connect(db)
    init_handoff_audit(conn)
    init_tool_audit(conn)
    h = Handoff(from_agent="ana", to_agent="researcher", payload={"task": {"q": "x"}})
    record_handoff(conn, h, "routed", session_id="s1")
    record_tool_call(conn, session_id="s1", agent="researcher", tool="search",
                     args={"q": "x"}, result='"foo"', outcome="ok")
    conn.commit()
    doc = TeamLoader({"ana", "researcher"}).load(str(pack))
    return conn, TeamRegistry(doc)


def test_replay_succeeds_when_routes_unchanged(db_with_team):
    conn, registry = db_with_team
    report = replay_session(conn, session_id="s1", registry=registry)
    assert report.handoffs_replayed == 1
    assert report.tools_replayed == 1
    assert report.mismatches == []


def test_replay_detects_routing_change(tmp_path):
    pack_a = tmp_path / "v1.md"
    pack_a.write_text(
        "---\nname: t\nversion: '1'\nmanager: ana\n"
        "members: [ana, researcher]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, researcher: 0.5}}\n---\n"
    )
    db = tmp_path / "c.db"
    conn = sqlite3.connect(db)
    init_handoff_audit(conn)
    init_tool_audit(conn)
    # Record handoff against v1 where target was researcher
    h = Handoff(from_agent="ana", to_agent="researcher", payload={})
    record_handoff(conn, h, "routed", session_id="s1")
    # Replay against v2 (members list excludes researcher → unknown_target)
    pack_b = tmp_path / "v2.md"
    pack_b.write_text(
        "---\nname: t\nversion: '2'\nmanager: ana\n"
        "members: [ana, pm]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, pm: 0.5}}\n---\n"
    )
    doc_b = TeamLoader({"ana", "pm"}).load(str(pack_b))
    report = replay_session(conn, session_id="s1", registry=TeamRegistry(doc_b))
    assert report.mismatches != []
    assert any(isinstance(m, ReplayMismatch) and m.kind == "route" for m in report.mismatches)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/conexus/tests/test_framework_replay.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write implementation**

```python
# src/conexus/core/team/replay.py
"""Deterministic replay of handoff_audit + tool_audit traces against a current pack.

Replay re-routes each recorded Handoff through HandoffRouter against the supplied
TeamRegistry. If the resolved target differs from the recorded outcome, a
ReplayMismatch is collected. Tool calls are not re-executed (no side effects);
they are replayed as identity checks (recorded result is read back). Future work
(spec §1.7 hardening): full LLM-call replay against frozen prompts.
"""
from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any
from conexus.core.team.handoff import Handoff
from conexus.core.team.handoff_router import HandoffRouter
from conexus.core.team.team_registry import TeamRegistry


@dataclass
class ReplayMismatch:
    kind: str       # "route" | "missing_member"
    expected: Any
    actual: Any
    detail: str = ""


@dataclass
class ReplayReport:
    handoffs_replayed: int = 0
    tools_replayed: int = 0
    mismatches: list[ReplayMismatch] = field(default_factory=list)


def replay_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    registry: TeamRegistry,
) -> ReplayReport:
    """Replay all rows in handoff_audit + tool_audit for the given session_id.

    Both tables now carry session_id (added in Task 6). Legacy rows persisted
    with session_id='legacy' are skipped unless the caller explicitly passes
    session_id='legacy'.
    """
    report = ReplayReport()
    router = HandoffRouter(registry, conn=None)  # do not write fresh audit during replay

    for row in conn.execute(
        "SELECT payload_json, outcome FROM handoff_audit WHERE session_id=? ORDER BY id",
        (session_id,),
    ):
        payload_json, recorded_outcome = row
        h = Handoff.model_validate_json(payload_json)
        try:
            actual_target = router.route(h)
            actual_outcome = "routed"
        except ValueError as exc:
            actual_target = None
            actual_outcome = "unknown_target" if h.to_agent != "auto" else "no_match"
            _ = exc

        if actual_outcome != recorded_outcome:
            report.mismatches.append(ReplayMismatch(
                kind="route",
                expected=recorded_outcome,
                actual=actual_outcome,
                detail=f"{h.from_agent}→{h.to_agent} (target={actual_target})",
            ))
        report.handoffs_replayed += 1

    for row in conn.execute(
        "SELECT tool, agent FROM tool_audit WHERE session_id=? ORDER BY id",
        (session_id,),
    ):
        tool, agent = row
        if not registry.has_member(agent):
            report.mismatches.append(ReplayMismatch(
                kind="missing_member",
                expected=agent,
                actual=None,
                detail=f"tool {tool} recorded for absent member {agent}",
            ))
        report.tools_replayed += 1

    return report
```

- [ ] **Step 4: Add CLI subcommand**

```python
# src/conexus/cli/__main__.py — add handler + parser

def _handle_replay(args):
    import sqlite3
    from conexus.core.team.replay import replay_session
    from conexus.core.team.team_loader import TeamLoader
    from conexus.core.team.team_registry import TeamRegistry
    available = set(filter(None, (args.available_agents or "").split(",")))
    doc = TeamLoader(available).load(args.pack)
    conn = sqlite3.connect(args.db)
    report = replay_session(conn, session_id=args.session, registry=TeamRegistry(doc))
    print(f"handoffs replayed: {report.handoffs_replayed}")
    print(f"tools replayed:    {report.tools_replayed}")
    if report.mismatches:
        print(f"MISMATCHES ({len(report.mismatches)}):")
        for m in report.mismatches:
            print(f"  [{m.kind}] expected={m.expected} actual={m.actual}  {m.detail}")
        return 1
    print("OK — no mismatches.")
    return 0
```

Add parser inside `main()`:
```python
    replay_p = sub.add_parser("replay", help="Replay frozen audit traces against current pack")
    replay_p.add_argument("db", help="path to conexus.db")
    replay_p.add_argument("pack", help="path to TEAM_PACK.md")
    replay_p.add_argument("--session", default="default", help="session_id to replay (tool_audit only)")
    replay_p.add_argument("--available-agents", default="")
    replay_p.set_defaults(func=_handle_replay)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest src/conexus/tests/test_framework_replay.py src/conexus/tests/test_framework_cli.py -v`
Expected: 2 + existing CLI PASS.

- [ ] **Step 6: Commit**

```bash
git add src/conexus/core/team/replay.py src/conexus/cli/__main__.py src/conexus/tests/test_framework_replay.py
git commit -m "feat(phase-9): replay_session + 'conexus replay' CLI (T-032)"
```

---

### Task 8: McpStdioBackend — JSON-RPC id correlation reader (T-035)

**Files:**
- Modify: `src/conexus/core/backends/mcp_stdio_backend.py`
- Test: `src/conexus/tests/test_framework_mcp_stdio_correlation.py` (NEW)

- [ ] **Step 1: Write the failing test**

```python
# src/conexus/tests/test_framework_mcp_stdio_correlation.py
"""McpStdioBackend must correlate JSON-RPC responses by id when notifications interleave."""
from __future__ import annotations
import asyncio
import json
import pytest
from conexus.core.backends.mcp_stdio_backend import McpStdioBackend


class _FakeProc:
    """Stdin/stdout pair that emits a notification before the real response."""
    def __init__(self):
        self.stdin = self  # we write request bytes here, ignore them
        self.stdout = self
        self._inbox = asyncio.Queue()
        self._closed = False

    def write(self, data):
        try:
            req = json.loads(data.decode().strip())
        except Exception:
            return
        # Emit a notification first (no id), then the response with matching id
        self._inbox.put_nowait((json.dumps({"jsonrpc": "2.0", "method": "log/message",
                                             "params": {"level": "info", "msg": "hi"}}) + "\n").encode())
        if req["method"] == "initialize":
            self._inbox.put_nowait((json.dumps({"jsonrpc": "2.0", "id": req["id"],
                                                 "result": {}}) + "\n").encode())
        elif req["method"] == "tools/list":
            self._inbox.put_nowait((json.dumps({"jsonrpc": "2.0", "id": req["id"],
                                                 "result": {"tools": [{"name": "ping"}]}}) + "\n").encode())

    async def drain(self):
        return None

    async def readline(self):
        return await self._inbox.get()

    def terminate(self):
        self._closed = True

    async def wait(self):
        return 0


@pytest.mark.asyncio
async def test_correlation_skips_notifications(monkeypatch):
    backend = McpStdioBackend(["dummy"])

    async def fake_create(*args, **kwargs):
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    await backend.start()
    assert backend.list_tools() == ["ping"]
    await backend.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/conexus/tests/test_framework_mcp_stdio_correlation.py -v`
Expected: FAIL — current readline() returns the notification, JSON has no "result" → KeyError or wrong-id parse.

- [ ] **Step 3: Rewrite _call with asyncio.Lock + id correlation**

```python
# src/conexus/core/backends/mcp_stdio_backend.py — modify __init__ and replace _call

    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        self._command = command
        self._env = env
        self._proc: asyncio.subprocess.Process | None = None
        self._id = 0
        self._initialized = False
        self._tool_names: list[str] = []
        self._call_lock = asyncio.Lock()  # serialize _call to avoid id-race

    async def _call(self, method: str, params: dict) -> Any:
        assert self._proc and self._proc.stdin and self._proc.stdout
        async with self._call_lock:
            self._id += 1
            req_id = self._id
            req = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
            self._proc.stdin.write((req + "\n").encode())
            await self._proc.stdin.drain()

            # Drain frames until we see a JSON-RPC response with our id.
            # Notifications (no "id" field) are silently dropped — Phase 9
            # does not surface server-side log/message frames.
            # Lock guarantees no concurrent _call → no stale-id case in Phase 9.
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    raise RuntimeError("MCP server closed stdout")
                try:
                    frame = json.loads(line.decode())
                except json.JSONDecodeError:
                    continue
                if "id" not in frame:
                    continue  # notification — ignore
                if frame["id"] != req_id:
                    continue  # defensive: ignore stale frame (lock should prevent this)
                if "error" in frame:
                    raise RuntimeError(f"MCP error: {frame['error']}")
                return frame.get("result")
```

Add concurrency test:

```python
# append to src/conexus/tests/test_framework_mcp_stdio_correlation.py
@pytest.mark.asyncio
async def test_concurrent_calls_serialize_via_lock(monkeypatch):
    """Two concurrent _call invocations must not interleave their ids."""
    backend = McpStdioBackend(["dummy"])

    async def fake_create(*a, **kw):
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    await backend.start()

    # Issue 5 concurrent tools/list calls; lock must serialize. No assertion
    # about content — the success criterion is that neither raises a stale-id
    # error and all return the same result.
    results = await asyncio.gather(*(backend._call("tools/list", {}) for _ in range(5)))
    assert all(r == {"tools": [{"name": "ping"}]} for r in results)
    await backend.stop()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest src/conexus/tests/test_framework_mcp_stdio_correlation.py src/conexus/tests/test_framework_backends.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conexus/core/backends/mcp_stdio_backend.py src/conexus/tests/test_framework_mcp_stdio_correlation.py
git commit -m "fix(phase-9): McpStdioBackend correlates JSON-RPC by id, skips notifications (T-035)"
```

---

### Task 9: MCPProducer — FastMCP server exposing wiki + Conexus tools (T-033)

**Files:**
- Create: `src/conexus/core/mcp/__init__.py`
- Create: `src/conexus/core/mcp/producer.py`
- Modify: `src/conexus/cli/__main__.py` — add `mcp-server` subcommand.
- Modify: `pyproject.toml` — add `fastmcp>=0.5`.
- Test: `src/conexus/tests/test_framework_mcp_producer.py` (NEW)

- [ ] **Step 1: Add dependency**

Edit `pyproject.toml`, add to `[project] dependencies`:
```
"fastmcp>=0.5",
```

Run: `uv sync`
Expected: fastmcp installs.

- [ ] **Step 2: Create package marker**

```python
# src/conexus/core/mcp/__init__.py
"""MCP integration package — Conexus as MCP server (Producer) for Claude Code."""
```

- [ ] **Step 3: Write the failing tests (§9 acceptance: tool + resource + bearer round-trip)**

```python
# src/conexus/tests/test_framework_mcp_producer.py
"""MCPProducer §9 acceptance: tool + wiki:// resource + bearer auth round-trip."""
from __future__ import annotations
import asyncio
import pytest
from conexus.core.mcp.producer import (
    build_mcp_producer,
    check_bearer,
    BearerError,
)


def test_producer_exposes_wiki_search_tool(tmp_path):
    server = build_mcp_producer(wiki_root=str(tmp_path), bearer_token="t")
    tool_names = {t.name for t in asyncio.run(server.list_tools())}
    assert "wiki_search" in tool_names


def test_producer_exposes_wiki_resource(tmp_path):
    """wiki:// resource must be readable per spec §1.7."""
    (tmp_path / "page.md").write_text("hello world", encoding="utf-8")
    server = build_mcp_producer(wiki_root=str(tmp_path), bearer_token="t")
    resources = asyncio.run(server.list_resources())
    uris = {str(r.uri) for r in resources}
    assert any(u.startswith("wiki://") for u in uris)


def test_producer_requires_bearer_token():
    with pytest.raises(ValueError):
        build_mcp_producer(wiki_root="/tmp", bearer_token="")


def test_check_bearer_accepts_correct_token():
    check_bearer("Bearer abc", expected="abc")  # no raise


def test_check_bearer_rejects_missing():
    with pytest.raises(BearerError):
        check_bearer(None, expected="abc")


def test_check_bearer_rejects_wrong_scheme():
    with pytest.raises(BearerError):
        check_bearer("Basic abc", expected="abc")


def test_check_bearer_rejects_wrong_token():
    with pytest.raises(BearerError):
        check_bearer("Bearer wrong", expected="abc")


def test_check_bearer_constant_time():
    """check_bearer must use compare_digest (smoke check — exact value not asserted)."""
    # Two calls with same wrong token should both raise (no information leak)
    with pytest.raises(BearerError):
        check_bearer("Bearer wrong1", expected="rightxxxxxxxx")
    with pytest.raises(BearerError):
        check_bearer("Bearer wrong2", expected="rightxxxxxxxx")


def test_verify_bearer_tool_round_trip(tmp_path):
    """End-to-end: client invokes verify_bearer tool with valid + invalid tokens."""
    server = build_mcp_producer(wiki_root=str(tmp_path), bearer_token="secret-abc")
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert "verify_bearer" in tools

    # Valid token — call resolves successfully
    result = asyncio.run(server.call_tool("verify_bearer", {"token": "secret-abc"}))
    # FastMCP normalizes return values; assert non-error path
    assert result is not None

    # Invalid token — must raise (BearerError surfaces as MCP error)
    with pytest.raises(Exception):
        asyncio.run(server.call_tool("verify_bearer", {"token": "wrong"}))
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest src/conexus/tests/test_framework_mcp_producer.py -v`
Expected: FAIL — module missing.

- [ ] **Step 5: Implement producer (tool + wiki:// resource + bearer check)**

```python
# src/conexus/core/mcp/producer.py
"""MCPProducer — exposes Conexus capabilities as an MCP server.

Phase 9 scope: stdio transport + bearer-token gate + wiki_search tool +
wiki:// resource (per spec §1.7 + §9 acceptance). Streamable HTTP transport
and full scope-based access control are deferred to a future hardening phase
(documented in plan's Phase 9 Scope Decision section).
"""
from __future__ import annotations
import hmac
from pathlib import Path
from typing import Any

try:
    from fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise ImportError("fastmcp not installed; run `uv sync`") from exc


class BearerError(Exception):
    """Raised when bearer header is missing or invalid."""


def check_bearer(authorization_header: str | None, *, expected: str) -> None:
    """Validate `Authorization: Bearer <expected>` header.

    Uses hmac.compare_digest for constant-time comparison.
    Raises BearerError on missing, wrong scheme, or wrong token.
    """
    if not authorization_header:
        raise BearerError("missing Authorization header")
    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0] != "Bearer":
        raise BearerError("expected 'Bearer <token>' scheme")
    if not hmac.compare_digest(parts[1], expected):
        raise BearerError("invalid bearer token")


def build_mcp_producer(*, wiki_root: str, bearer_token: str) -> FastMCP:
    """Build MCPProducer with bearer-token integration into the MCP request path.

    Stdio has no transport-level Authorization header, so Phase 9 surfaces the
    bearer check as a first-class MCP tool `verify_bearer(token)`. Clients
    (Claude Code) call this immediately after `initialize` to confirm the
    server-side token matches what they were configured with. Future hardening
    (Streamable HTTP transport) will additionally enforce bearer in the HTTP
    Authorization header — `check_bearer` is the shared implementation.
    """
    if not bearer_token:
        raise ValueError("bearer_token must be non-empty")

    mcp = FastMCP("conexus")
    root = Path(wiki_root)

    @mcp.tool()
    def verify_bearer(token: str) -> dict[str, bool]:
        """Bearer-token round-trip per spec §9 acceptance.

        Returns {"ok": true} when token matches; raises BearerError otherwise.
        """
        check_bearer(f"Bearer {token}", expected=bearer_token)
        return {"ok": True}

    @mcp.tool()
    def wiki_search(query: str) -> list[dict[str, Any]]:
        """Search wiki markdown for literal `query` substring. Returns up to 20 hits."""
        hits: list[dict[str, Any]] = []
        if not root.exists():
            return hits
        for f in root.rglob("*.md"):
            try:
                text = f.read_text(encoding="utf-8")
            except Exception:
                continue
            if query in text:
                hits.append({"path": str(f.relative_to(root)), "size": len(text)})
                if len(hits) >= 20:
                    break
        return hits

    @mcp.resource("wiki://{path}")
    def wiki_page(path: str) -> str:
        """Return the raw markdown of a wiki page by relative path.

        Path is sandboxed to wiki_root; traversal attempts raise.
        """
        target = (root / path).resolve()
        if not str(target).startswith(str(root.resolve())):
            raise ValueError("path outside wiki_root")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(path)
        return target.read_text(encoding="utf-8")

    return mcp
```

- [ ] **Step 6: Add CLI subcommand**

```python
# src/conexus/cli/__main__.py — add handler + parser

def _handle_mcp_server(args):
    import os
    from conexus.core.mcp.producer import build_mcp_producer
    token = os.environ.get("CONEXUS_MCP_TOKEN", "")
    if not token:
        raise SystemExit("CONEXUS_MCP_TOKEN env var required")
    server = build_mcp_producer(wiki_root=args.wiki_root, bearer_token=token)
    server.run(transport="stdio")
```

```python
    mcp_p = sub.add_parser("mcp-server", help="Run Conexus as an MCP server (stdio)")
    mcp_p.add_argument("--wiki-root", default="./data/wiki")
    mcp_p.set_defaults(func=_handle_mcp_server)
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest src/conexus/tests/test_framework_mcp_producer.py -v`
Expected: 9 PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/conexus/core/mcp/ src/conexus/cli/__main__.py src/conexus/tests/test_framework_mcp_producer.py
git commit -m "feat(phase-9): MCPProducer scaffold + wiki_search tool + 'conexus mcp-server' CLI (T-033)"
```

---

### Task 10: pip-install smoke test + deployment field round-trip (T-034)

**Files:**
- Create: `src/conexus/tests/test_framework_pip_install.py`

- [ ] **Step 1: Write the test**

```python
# src/conexus/tests/test_framework_pip_install.py
"""Pip-install smoke test + deployment field round-trip (Codex B-7 + B-8)."""
from __future__ import annotations
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest


@pytest.mark.slow
def test_pip_install_wheel_works(tmp_path):
    """Build wheel + install in a fresh venv + import conexus.cli.__main__."""
    repo_root = Path(__file__).resolve().parents[3]
    wheel_dir = tmp_path / "dist"
    wheel_dir.mkdir()
    subprocess.check_call(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(wheel_dir)],
        cwd=str(repo_root),
    )
    wheels = list(wheel_dir.glob("conexus-*.whl"))
    assert wheels, "no wheel produced"
    venv_dir = tmp_path / "venv"
    subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
    pip = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    py = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    subprocess.check_call([str(pip), "install", str(wheels[0])])
    subprocess.check_call([str(py), "-c", "from conexus.cli import __main__"])


def test_deployment_field_round_trips(tmp_path):
    """deployment: in TEAM_PACK frontmatter survives parse → registry."""
    from conexus.core.team.team_loader import TeamLoader
    from conexus.core.team.team_registry import TeamRegistry
    p = tmp_path / "TEAM_PACK.md"
    p.write_text(
        "---\n"
        "name: t\nversion: '1'\nmanager: ana\nmembers: [ana, pm]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, pm: 0.5}}\n"
        "deployment:\n"
        "  region: gru\n"
        "  process: telegram\n"
        "---\n"
    )
    doc = TeamLoader({"ana", "pm"}).load(str(p))
    assert doc.frontmatter.deployment == {"region": "gru", "process": "telegram"}
```

- [ ] **Step 2: Run only the round-trip test (skip slow pip install in CI by default)**

Run: `uv run pytest src/conexus/tests/test_framework_pip_install.py::test_deployment_field_round_trips -v`
Expected: PASS.

> The pip-install smoke test is marked `@pytest.mark.slow` because it builds a wheel + creates a venv. Run on demand with `uv run pytest -m slow`. Per dev-workflow §05, slow tests are gated to release prep, not per-commit.

- [ ] **Step 3: Commit**

```bash
git add src/conexus/tests/test_framework_pip_install.py
git commit -m "test(phase-9): pip-install smoke + deployment field round-trip (T-034)"
```

---

### Task 11: Wiki-keeper sync

**Files:**
- Modify: `docs/wiki/agents-framework/06-multi-agent.md` (or whichever partition holds team docs)
- Modify: `docs/wiki/agents-framework/13-trifecta.md` for `clear_boundary` section.
- Modify: `docs/wiki/agents-framework/14-replay.md` (NEW partition or add to 13).

- [ ] **Step 1: Dispatch wiki-keeper subagent**

Use the `Agent` tool with `subagent_type: wiki-keeper`. Prompt:

```
Phase 9 just landed. Update docs/wiki/agents-framework partitions to reflect:
1. handle_team_message — the new multi-agent loop (delegate_to_<agent> tool, context_mode trim, return_on stack-return, termination_text). See src/conexus/core/agent_handler.py.
2. trust_boundary_cleared is now Optional[str] (reason). New TrifectaGuard.clear_boundary(reason). See src/conexus/core/trifecta/guard.py and src/conexus/core/team/handoff.py.
3. tool_audit table + replay_session(). See src/conexus/core/memory/tool_audit.py and src/conexus/core/team/replay.py. Add a Replay section.
4. MCPProducer (stdio, FastMCP, wiki_search tool). See src/conexus/core/mcp/producer.py.
5. McpStdioBackend now id-correlates JSON-RPC. See src/conexus/core/backends/mcp_stdio_backend.py.
6. TeamPolicy.max_parallel_members default 1.

Cite line numbers. Do not invent. Read each source file before writing.
```

- [ ] **Step 2: Review wiki-keeper diff**

Inspect the diff. Reject any invented or speculative content. Re-dispatch with corrections if needed.

- [ ] **Step 3: Commit**

```bash
git add docs/wiki/agents-framework/
git commit -m "docs(wiki): Phase 9 partition sync — team loop + replay + MCP + trust-clear reason"
```

---

### Task 12: Phase 9 integration regression + roadmap update

**Files:**
- Modify: `.brain/roadmap.json` (mark T-028..T-035 done; phase-9 → completed; current_phase_id → null or next phase id)
- Modify: `.brain/system-pulse.md`
- Modify: `.brain/session-log.md`

- [ ] **Step 1: Run batched framework tests**

```bash
uv run pytest \
  src/conexus/tests/test_framework_handoff.py \
  src/conexus/tests/test_framework_team_pack.py \
  src/conexus/tests/test_framework_handoff_router.py \
  src/conexus/tests/test_framework_budget_cascader.py \
  src/conexus/tests/test_framework_team_trifecta.py \
  src/conexus/tests/test_framework_team_integration.py \
  src/conexus/tests/test_framework_cli.py \
  src/conexus/tests/test_framework_backends.py \
  src/conexus/tests/test_framework_trifecta.py \
  src/conexus/tests/test_framework_trifecta_integration.py \
  src/conexus/tests/test_framework_trust_clear.py \
  src/conexus/tests/test_framework_delegate_tool.py \
  src/conexus/tests/test_framework_transcript.py \
  src/conexus/tests/test_framework_team_loop.py \
  src/conexus/tests/test_framework_team_loop_termination.py \
  src/conexus/tests/test_framework_tool_audit.py \
  src/conexus/tests/test_framework_replay.py \
  src/conexus/tests/test_framework_mcp_stdio_correlation.py \
  src/conexus/tests/test_framework_mcp_producer.py \
  src/conexus/tests/test_framework_pip_install.py::test_deployment_field_round_trips \
  -v
```

Expected: ALL PASS.

- [ ] **Step 2: Run ruff**

```bash
uv run ruff check src/conexus/
```

Expected: clean.

- [ ] **Step 3: Update `.brain/roadmap.json`**

For each of T-028..T-035: set `"status": "done"` + `"completed_at": "2026-04-30T..."`. Set phase-9 status `completed`. Update summary counts. If no next phase, set `current_phase_id: null`.

- [ ] **Step 4: Update system-pulse + session-log**

Use the `nexus:nexus-checkpoint` skill conventions. Note Phase 9 deliverables, the Phase 9 Scope Decision (replay = handoff+tool only; HTTP transport deferred), and the next-phase candidates.

- [ ] **Step 5: Commit**

```bash
git add .brain/
git commit -m "docs(brain): Phase 9 complete — multi-agent loop + replay + MCPProducer"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- §1.6 delegate_to_<agent> + context_mode + return_on + hop counter → Tasks 2, 3, 5 ✅
- §1.7 MCPProducer → Task 9 ✅ (stdio only — Streamable HTTP deferred)
- §1.8 cross-agent Trifecta + clear_boundary → Task 1 ✅
- §1.9 max_parallel_members + termination_text → Tasks 4, 5 ✅
- §9 Replay acceptance → Tasks 6, 7 ✅
- McpStdioBackend hardening (Phase 8 known risk) → Task 8 ✅
- pip-install smoke + deployment round-trip → Task 10 ✅

**2. Placeholder scan:** none. Every step has either runnable code, exact commands, or precise file references.

**3. Type consistency:**
- `handle_team_message` signature: keyword-only — matches both test rigs.
- `Handoff.trust_boundary_cleared: str | None` — used identically in guard.py + audit.py + tests.
- `ReplayReport` dataclass fields used identically in test + impl.
- `build_delegate_schemas(registry, current_agent)` arg order matches calls in agent_handler.py.
- `record_tool_call` keyword-only signature consistent in test + use sites.

**4. Test order:** Tasks 1-4 are isolated and can run in any order after T-031 (Task 1) lands. Task 5 depends on 1+2+3+4. Tasks 6+7 (replay) independent of 5. Task 8 (mcp_stdio) independent. Task 9 (MCPProducer) independent. Task 10 independent. Task 11 (wiki) after all impl. Task 12 (regression + brain) last.

**Suggested parallel-friendly grouping for subagent-driven dispatch:**
- Wave A (parallel-safe; different files): T-031 (Task 1), T-035 (Task 8), T-033 (Task 9), T-034 (Task 10), tool_audit foundation (Task 6).
- Wave B (sequential after Wave A; touches agent_handler.py): T-028 part 1 (Task 2), then T-029 part 1 (Task 3), then T-030 part 1 (Task 4), then loop wiring (Task 5 — depends on Tasks 1+2+3+4+6).
- Wave C (after Wave B): T-032 replay runner (Task 7 — needs handoff_audit session_id from Task 6).
- Wave D (after all impl): wiki (Task 11), brain + regression (Task 12).

---

## Execution Handoff

Plan saved at `docs/superpowers/plans/2026-04-30-phase-9-runtime-replay-mcp.md`.

Codex pre-validate before starting Wave A: run `/codex:rescue` with this plan path. If codex flags blockers, address in plan before dispatch.

Two execution options:

1. **Subagent-Driven (recommended)** — fresh implementer per task, two-stage review per task, batched parallel waves.
2. **Inline Execution** — same session, batch checkpoints.

Which approach?
