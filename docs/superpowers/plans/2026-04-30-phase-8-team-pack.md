# Phase 8 — TEAM_PACK + BudgetCascader + HandoffRouter + Cross-Agent Trifecta — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Conexus from one-agent-at-a-time into a team of agents with versioned `Handoff`, edge-based `HandoffRouter`, shared `BudgetCascader`, and security-taint propagation across agent boundaries.

**Architecture:** New `src/conexus/core/team/` package with five focused modules: `handoff.py` (Pydantic type), `team_pack.py` (YAML parser), `team_loader.py` + `team_registry.py` (runtime state), `handoff_router.py` (edges → manager fallback), `budget_cascader.py` (pool + per-share policies). `agent_handler.py` extended to accept seed-taint from incoming `Handoff`. `agent_registry.py` extended to support N backends per agent (foundation prep). One reference team pack (`agents/teams/product_team/`) ships alongside.

**Tech Stack:** Python 3.12, Pydantic 2.x, PyYAML, SQLite, pytest-asyncio.

**Spec:** [docs/superpowers/specs/2026-04-29-conexus-framework-v2.md](docs/superpowers/specs/2026-04-29-conexus-framework-v2.md) §1.2, §1.5, §1.6, §1.8, §1.9, §5, §8 (Phase 8 row), §9 (acceptance).

---

## Decisions (override at top of plan, not inside tasks)

| ID | Decision | Default | Reason |
|----|----------|---------|--------|
| D1 | Reference team membership | ana + pm + researcher (3) | Spec §9 acceptance: ≥3 members |
| D2 | Manager LLM | Same `TrackedLLM` as `pm` member | No dedicated cheap router; manager role = pm with edges |
| D3 | `borrow_from_pool` policy | Full impl v1 (counter-shift) | Spec §1.5 lists all 3 policies; stub = under-deliver |
| D4 | Plan split | Single Phase 8 plan | One acceptance gate; smaller plan = lower coordination cost |
| D5 | Subagent models | Sonnet default; Haiku for mechanical-only (CLI wiring, fixture additions, doc imports) | Per `docs/dev-workflow/01-model-routing.md` |
| D6 | Codex validation | Twice — pre-phase + pre-phase-review | Per `docs/dev-workflow/03-codex-validation.md` mandatory triggers |
| D7 | Wiki sync | Existing `wiki-keeper` subagent (Sonnet-pinned), called after T10 | Per `docs/dev-workflow/05-quality-gates.md` per-phase gate |
| D8 | Foundation prep order | T0 (multi-backend AgentRegistry) ships before any team work | Phase 7 collapsed multi-skill → last-registered; team will load multi-skill agents |

---

## File Structure

### Create

| File | Responsibility |
|------|----------------|
| `src/conexus/core/team/__init__.py` | Package marker |
| `src/conexus/core/team/handoff.py` | `Handoff` Pydantic v2 model — versioned, hop-counted, taint-bearing |
| `src/conexus/core/team/team_pack.py` | `TeamPackDocument`, `parse_team_pack(path)` |
| `src/conexus/core/team/team_loader.py` | `TeamLoader` — validates members exist, wires edges + budget |
| `src/conexus/core/team/team_registry.py` | `TeamRegistry` — runtime state, member→agent mapping, hop tracking |
| `src/conexus/core/team/handoff_router.py` | `HandoffRouter.route(handoff) -> str` — edges first, manager LLM fallback |
| `src/conexus/core/team/budget_cascader.py` | `BudgetCascader` — pool + per-share + 3 `on_share_exceeded` policies |
| `src/conexus/core/memory/handoff_audit.py` | SQLite `handoff_audit` writer + `tool_audit` cross-agent extension |
| `agents/teams/product_team/TEAM_PACK.md` | Reference team pack (D1) |
| `agents/teams/product_team/__init__.py` | Empty package marker |
| `src/conexus/tests/test_framework_team_handoff.py` | Handoff Pydantic shape + serialization |
| `src/conexus/tests/test_framework_team_pack.py` | TEAM_PACK parser + TeamLoader |
| `src/conexus/tests/test_framework_team_router.py` | HandoffRouter edges + manager fallback |
| `src/conexus/tests/test_framework_budget_cascader.py` | Pool + share enforcement + 3 policies |
| `src/conexus/tests/test_framework_team_trifecta.py` | Cross-agent taint propagation |
| `src/conexus/tests/test_framework_team_integration.py` | Full team flow E2E |

### Modify

| File | Change |
|------|--------|
| `src/conexus/core/agent_registry.py` | Multi-backend per agent (T0). Backend list + tool-name index. |
| `src/conexus/core/agent_handler.py` | Accept `Handoff` seed-taint via `AgentHandlerConfig.incoming_handoff`; `trust_boundary_cleared` field |
| `src/conexus/core/trifecta/guard.py` | Constructor accepts seed taint set |
| `src/conexus/core/trifecta/tags.py` | Re-export for `Handoff.tags` use |
| `src/conexus/core/skills/skill_resolver.py` | Use `register_backend` (already plural-safe after T0) |
| `src/conexus/cli/__main__.py` | `conexus run team <name>` subcommand |
| `src/conexus/core/memory/sqlite_store.py` | Migration: `handoff_audit` table |

---

## Subagent Dispatch Convention

Per `docs/dev-workflow/01-model-routing.md` and user direction:

| Role | Model | When |
|------|-------|------|
| Implementer | Sonnet | Default for every implementation task below |
| Implementer (mechanical) | Haiku | Tasks marked **[mechanical]** — CLI flag wiring (T7), fixture-only additions, import re-exports |
| Spec reviewer | Haiku | After every implementer; checks code matches spec section cited in task |
| Code-quality reviewer | Haiku | Parallel with spec reviewer; checks `/simplify` compliance, ruff, no over-engineering |
| Phase reviewer | Opus | T11 only — full plan vs. spec + codex log |
| Wiki-keeper | Sonnet (pinned in subagent def) | T10 |
| Codex validator | `codex:codex-rescue` | Pre-phase (before T0) and pre-phase-review (before T11) |

Implementers run **sequentially** (per `subagent-driven-development` skill — git conflicts on parallel implementers). Spec + quality reviewers run **parallel** after implementer (independent reads). Tasks themselves are sequenced by dependencies (T0 → T1 → T2 → … → T10 → T11).

---

## Codex Pre-Phase Gate

Before T0, dispatch `codex:codex-rescue` with this plan + the v2 spec. Look for:
- Spec coverage gaps (every §1.5/§1.6/§1.8/§1.9 requirement → at least one task)
- Type-name consistency across tasks
- Infeasible orderings (e.g. Handoff used before defined)
- Multi-backend design holes

Log verdict in `## Codex log` section at end of this plan.

---

## Task 0: AgentRegistry — Multi-Backend Per Agent (Foundation)

**Why:** Phase 7 left `_backends: dict[str, ToolBackend]` — registering N skills on same agent collapses to last. Team mode loads many skills per member; must fix first.

**Routing contract:** every backend declares its tool manifest via `list_tools()`. Registry dispatches on declared names — non-Python backends (mcp-stdio) must enumerate; "default = always try" is rejected (codex pre-phase finding, 2026-04-30).

**Files:**
- Modify: `src/conexus/core/backends/base.py` (add `list_tools()` abstract)
- Modify: `src/conexus/core/backends/python_backend.py` (impl from `tools_schema` or dir())
- Modify: `src/conexus/core/backends/mcp_stdio.py` (cache tools/list response from MCP handshake)
- Modify: `src/conexus/core/agent_registry.py`
- Modify: `src/conexus/tests/test_framework_backends.py` (extend, don't rewrite)

- [ ] **Step 1: Write failing tests for multi-backend registration + manifest contract**

```python
# Append to src/conexus/tests/test_framework_backends.py
class _ToolsA:
    def alpha(self) -> str: return "A"

class _ToolsB:
    def beta(self) -> str: return "B"

def test_python_backend_lists_tools():
    b = PythonBackend(_ToolsA())
    assert "alpha" in b.list_tools()

@pytest.mark.asyncio
async def test_registry_multi_backend_routes_by_tool_name():
    registry = AgentRegistry()
    registry.register_backend("bot", PythonBackend(_ToolsA()))
    registry.register_backend("bot", PythonBackend(_ToolsB()))
    a = await registry.execute_tool("bot", "alpha", {})
    b = await registry.execute_tool("bot", "beta", {})
    assert '"A"' in a
    assert '"B"' in b

@pytest.mark.asyncio
async def test_registry_multi_backend_collision_raises():
    registry = AgentRegistry()
    registry.register_backend("bot", PythonBackend(_ToolsA()))
    registry.register_backend("bot", PythonBackend(_ToolsA()))
    result = await registry.execute_tool("bot", "alpha", {})
    assert "tool collision" in result.lower()

@pytest.mark.asyncio
async def test_registry_unknown_tool_returns_error():
    registry = AgentRegistry()
    registry.register_backend("bot", PythonBackend(_ToolsA()))
    result = await registry.execute_tool("bot", "nonexistent", {})
    assert "tool desconhecida" in result.lower() or "unknown tool" in result.lower()
```

- [ ] **Step 2: Run tests, expect FAIL**

```
uv run pytest src/conexus/tests/test_framework_backends.py -v
```
Expected: 2 new failures (last-registered overwrites or collision passes silently).

- [ ] **Step 3a: Add list_tools() abstract to ToolBackend**

```python
# src/conexus/core/backends/base.py — modify
"""ToolBackend ABC — all backends implement this interface."""
from __future__ import annotations
from abc import ABC, abstractmethod


class ToolBackend(ABC):
    @abstractmethod
    async def execute(self, tool_name: str, args: dict) -> str:
        """Execute tool; return JSON string (success or {"error": ...})."""

    @abstractmethod
    def list_tools(self) -> list[str]:
        """Return tool names this backend handles. Used by registry for routing."""

    @property
    def backend_type(self) -> str:
        return "unknown"
```

- [ ] **Step 3b: Implement list_tools() in PythonBackend**

```python
# src/conexus/core/backends/python_backend.py — add method
def list_tools(self) -> list[str]:
    """Public callable methods on the underlying tools object."""
    return [
        n for n in dir(self._tools)
        if not n.startswith("_") and callable(getattr(self._tools, n))
    ]
```

- [ ] **Step 3c: Implement list_tools() in McpStdioBackend**

```python
# src/conexus/core/backends/mcp_stdio.py — cache tools/list response
# In start(): after handshake, call tools/list and store names:
#   self._tool_names = [t["name"] for t in resp["tools"]]
# Add method:
def list_tools(self) -> list[str]:
    return list(self._tool_names)
```

If `start()` not yet called, `_tool_names` defaults to `[]` (registry will return "tool desconhecida").

- [ ] **Step 3d: Implement multi-backend registry**

```python
# src/conexus/core/agent_registry.py — full rewrite
"""Agent registry — routes tool calls across N backends per agent."""
from __future__ import annotations
import json
from typing import Any
from conexus.core.backends.base import ToolBackend
from conexus.core.backends.python_backend import PythonBackend


class AgentRegistry:
    """Maps agent → list[ToolBackend]; tool-name → backend resolved at call time.

    Tool name uniqueness enforced per agent: collision returns an error instead of
    silently shadowing. Routing uses `backend.list_tools()` — no defaults-allowed.
    """

    def __init__(self) -> None:
        self._backends: dict[str, list[ToolBackend]] = {}

    def register(self, agent_name: str, tools: Any) -> None:
        """Backward-compat: register a Python tools object as a single backend."""
        self.register_backend(agent_name, PythonBackend(tools))

    def register_backend(self, agent_name: str, backend: ToolBackend) -> None:
        self._backends.setdefault(agent_name, []).append(backend)

    def get_tools(self, agent_name: str) -> Any:
        """Backward-compat: return underlying tools object of the first PythonBackend."""
        backends = self._backends.get(agent_name) or []
        for b in backends:
            if isinstance(b, PythonBackend):
                return b._tools
        raise KeyError(f"no PythonBackend for agent {agent_name!r}")

    def agent_names(self) -> list[str]:
        return list(self._backends.keys())

    async def execute_tool(self, agent_name: str, tool_name: str, args: dict) -> str:
        backends = self._backends.get(agent_name)
        if not backends:
            return json.dumps({"error": f"agente desconhecido: {agent_name}"})
        matches = [b for b in backends if tool_name in b.list_tools()]
        if not matches:
            return json.dumps({"error": f"tool desconhecida: {tool_name}"})
        if len(matches) > 1:
            return json.dumps({"error": f"tool collision: {tool_name} in {len(matches)} backends"})
        return await matches[0].execute(tool_name, args)
```

- [ ] **Step 4: Run all backend tests, expect PASS**

```
uv run pytest src/conexus/tests/test_framework_backends.py -v
```
Expected: all green (existing 6 + new 4: list_tools, multi-route, collision, unknown-tool).

- [ ] **Step 5: Run full suite to confirm no regression**

```
uv run pytest
```
Expected: 106 passed (102 baseline + 4 new).

- [ ] **Step 6: ruff + commit**

```bash
uv run ruff check src/conexus/
git add src/conexus/core/backends/base.py src/conexus/core/backends/python_backend.py src/conexus/core/backends/mcp_stdio.py src/conexus/core/agent_registry.py src/conexus/tests/test_framework_backends.py
git commit -m "feat(phase-8.0): AgentRegistry multi-backend + ToolBackend.list_tools() manifest"
```

---

## Task 1: `Handoff` Pydantic Type + Audit Table

**Files:**
- Create: `src/conexus/core/team/__init__.py` (empty)
- Create: `src/conexus/core/team/handoff.py`
- Create: `src/conexus/core/memory/handoff_audit.py`
- Modify: `src/conexus/core/memory/sqlite_store.py` (migration)
- Create: `src/conexus/tests/test_framework_team_handoff.py`

- [ ] **Step 1: Write failing tests**

```python
# src/conexus/tests/test_framework_team_handoff.py
import json
import pytest
from conexus.core.team.handoff import Handoff
from conexus.core.trifecta.tags import DataClass


def test_handoff_default_shape():
    h = Handoff(from_agent="ana", to_agent="pm", payload={"task": "design"})
    assert h.schema_version == "1"
    assert h.context_mode == "summary"
    assert h.return_on is None
    assert h.hop_count == 0
    assert h.max_hops == 5
    assert h.tags == set()
    assert h.trust_boundary_cleared is False


def test_handoff_carries_taint():
    h = Handoff(
        from_agent="researcher",
        to_agent="pm",
        payload={"summary": "..."},
        tags={DataClass.untrusted_read, DataClass.private_read},
    )
    assert DataClass.untrusted_read in h.tags
    assert DataClass.private_read in h.tags


def test_handoff_max_hops_enforced_at_increment():
    h = Handoff(from_agent="a", to_agent="b", payload={}, hop_count=4, max_hops=5)
    h2 = h.next_hop("c")
    assert h2.hop_count == 5
    with pytest.raises(ValueError, match="max_hops"):
        h2.next_hop("d")


def test_handoff_json_roundtrip():
    h = Handoff(from_agent="a", to_agent="b", payload={"x": 1}, tags={DataClass.untrusted_read})
    s = h.model_dump_json()
    h2 = Handoff.model_validate_json(s)
    assert h2 == h
```

- [ ] **Step 2: Run, expect FAIL** (`Handoff` undefined)

```
uv run pytest src/conexus/tests/test_framework_team_handoff.py -v
```

- [ ] **Step 3: Implement `Handoff`**

```python
# src/conexus/core/team/handoff.py
"""Handoff — typed, versioned payload passed between agents in a team."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from conexus.core.trifecta.tags import DataClass


class Handoff(BaseModel):
    """Cross-agent message carrying payload + trifecta taint + hop accounting."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    from_agent: str
    to_agent: str
    payload: dict[str, Any] = Field(default_factory=dict)
    context_mode: Literal["full", "last_message", "summary"] = "summary"
    return_on: str | None = None
    hop_count: int = 0
    max_hops: int = 5
    tags: set[DataClass] = Field(default_factory=set)
    trust_boundary_cleared: bool = False

    def next_hop(self, to_agent: str) -> "Handoff":
        new_count = self.hop_count + 1
        if new_count > self.max_hops:
            raise ValueError(f"max_hops exceeded ({self.max_hops})")
        return self.model_copy(update={"to_agent": to_agent, "hop_count": new_count, "from_agent": self.to_agent})
```

- [ ] **Step 4: Add audit table writer**

```python
# src/conexus/core/memory/handoff_audit.py
"""SQLite-backed audit log for cross-agent handoffs."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from conexus.core.team.handoff import Handoff

SCHEMA = """
CREATE TABLE IF NOT EXISTS handoff_audit (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL,
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
    conn.commit()


def record_handoff(conn: sqlite3.Connection, h: Handoff, outcome: str) -> None:
    conn.execute(
        "INSERT INTO handoff_audit (ts, from_agent, to_agent, hop_count, tags, trust_cleared, payload_json, outcome) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            h.from_agent,
            h.to_agent,
            h.hop_count,
            json.dumps(sorted(t.value for t in h.tags)),
            int(h.trust_boundary_cleared),
            h.model_dump_json(),
            outcome,
        ),
    )
    conn.commit()
```

- [ ] **Step 5: Wire migration into `SqliteStore.__init__`**

Add this line to `SqliteStore.__init__` after existing schema init (find by reading `src/conexus/core/memory/sqlite_store.py` and adding right before the closing of `__init__`):

```python
from conexus.core.memory.handoff_audit import init_handoff_audit
init_handoff_audit(self._conn)
```

- [ ] **Step 6: Run tests, expect PASS**

```
uv run pytest src/conexus/tests/test_framework_team_handoff.py -v
uv run pytest  # full suite no regression
```
Expected: 4 new pass; total 108 pass.

- [ ] **Step 7: ruff + commit**

```bash
uv run ruff check src/conexus/
git add src/conexus/core/team/ src/conexus/core/memory/handoff_audit.py src/conexus/core/memory/sqlite_store.py src/conexus/tests/test_framework_team_handoff.py
git commit -m "feat(phase-8.1): Handoff Pydantic type + handoff_audit table"
```

---

## Task 2: `TEAM_PACK.md` Parser + `TeamLoader`

**Files:**
- Create: `src/conexus/core/team/team_pack.py`
- Create: `src/conexus/core/team/team_loader.py`
- Create: `src/conexus/tests/test_framework_team_pack.py`

- [ ] **Step 1: Write failing tests**

```python
# src/conexus/tests/test_framework_team_pack.py
import pytest
from conexus.core.team.team_pack import parse_team_pack, TeamPackDocument
from conexus.core.team.team_loader import TeamLoader

PACK_MD = """---
name: product_team
version: 0.1.0
manager: pm
members: [ana, pm, researcher]
edges:
  - {from: pm, to: researcher, when: "task.kind == 'research'"}
  - {from: researcher, to: pm, auto: true}
budget:
  team_daily_usd: 1.00
  shares: {ana: 0.2, pm: 0.4, researcher: 0.4}
  on_share_exceeded: notify
policy:
  trifecta_enforcement: strict
  max_hops: 5
  max_turns: 20
  termination_text: DONE
---
Team body fragment.
"""


def test_parse_team_pack(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    doc = parse_team_pack(tmp_path / "TEAM_PACK.md")
    assert doc.frontmatter.name == "product_team"
    assert doc.frontmatter.manager == "pm"
    assert doc.frontmatter.members == ["ana", "pm", "researcher"]
    assert doc.frontmatter.edges[0]["from"] == "pm"
    assert doc.frontmatter.budget.team_daily_usd == 1.00
    assert doc.frontmatter.policy.max_hops == 5


def test_parse_missing_frontmatter_fails(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text("no frontmatter")
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        parse_team_pack(tmp_path / "TEAM_PACK.md")


def test_team_loader_validates_member_exists(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD.replace("[ana, pm, researcher]", "[ana, pm, ghost]"))
    available = {"ana", "pm", "researcher"}
    loader = TeamLoader(available_agents=available)
    with pytest.raises(ValueError, match="unknown member: ghost"):
        loader.load(tmp_path / "TEAM_PACK.md")


def test_team_loader_returns_document(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    loader = TeamLoader(available_agents={"ana", "pm", "researcher"})
    doc = loader.load(tmp_path / "TEAM_PACK.md")
    assert isinstance(doc, TeamPackDocument)
```

- [ ] **Step 2: Run, expect FAIL**

```
uv run pytest src/conexus/tests/test_framework_team_pack.py -v
```

- [ ] **Step 3: Implement parser**

```python
# src/conexus/core/team/team_pack.py
"""TEAM_PACK.md — YAML frontmatter parser. Mirrors pack_loader.py shape."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Literal
import yaml
from pydantic import BaseModel, Field


class TeamBudget(BaseModel):
    team_daily_usd: float
    shares: dict[str, float]
    on_share_exceeded: Literal["notify", "halt_member", "borrow_from_pool"] = "notify"


class TeamPolicy(BaseModel):
    trifecta_enforcement: Literal["strict", "warn", "off"] = "strict"
    max_hops: int = 5
    max_turns: int = 20
    termination_text: str = "DONE"


class TeamPackFrontmatter(BaseModel):
    name: str
    version: str
    manager: str | None = None
    members: list[str]
    edges: list[dict[str, Any]] = Field(default_factory=list)
    budget: TeamBudget
    policy: TeamPolicy = Field(default_factory=TeamPolicy)
    deployment: dict[str, str] = Field(default_factory=dict)


class TeamPackDocument(BaseModel):
    frontmatter: TeamPackFrontmatter
    body: str
    pack_dir: Path

    model_config = {"arbitrary_types_allowed": True}


def parse_team_pack(path: str | Path) -> TeamPackDocument:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{p}: missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{p}: missing YAML frontmatter")
    fm = TeamPackFrontmatter(**yaml.safe_load(parts[1]))
    return TeamPackDocument(frontmatter=fm, body=parts[2].strip(), pack_dir=p.parent)
```

- [ ] **Step 4: Implement loader**

```python
# src/conexus/core/team/team_loader.py
"""TeamLoader — validates a TEAM_PACK against available agents + budget shares."""
from __future__ import annotations
from pathlib import Path
from conexus.core.team.team_pack import parse_team_pack, TeamPackDocument


class TeamLoader:
    def __init__(self, available_agents: set[str]) -> None:
        self._available = available_agents

    def load(self, pack_path: str | Path) -> TeamPackDocument:
        doc = parse_team_pack(pack_path)
        unknown = [m for m in doc.frontmatter.members if m not in self._available]
        if unknown:
            raise ValueError(f"unknown member: {unknown[0]}")
        if doc.frontmatter.manager and doc.frontmatter.manager not in doc.frontmatter.members:
            raise ValueError(f"manager {doc.frontmatter.manager!r} not in members")
        share_total = sum(doc.frontmatter.budget.shares.values())
        if abs(share_total - 1.0) > 0.01:
            raise ValueError(f"budget shares must sum to 1.0 (got {share_total})")
        unknown_shares = set(doc.frontmatter.budget.shares) - set(doc.frontmatter.members)
        if unknown_shares:
            raise ValueError(f"share for unknown member(s): {sorted(unknown_shares)}")
        return doc
```

- [ ] **Step 5: Run, expect PASS**

```
uv run pytest src/conexus/tests/test_framework_team_pack.py -v
```

- [ ] **Step 6: ruff + commit**

```bash
uv run ruff check src/conexus/
git add src/conexus/core/team/team_pack.py src/conexus/core/team/team_loader.py src/conexus/tests/test_framework_team_pack.py
git commit -m "feat(phase-8.2): TEAM_PACK.md parser + TeamLoader (member + share validation)"
```

---

## Task 3: `TeamRegistry` Runtime State

**Files:**
- Create: `src/conexus/core/team/team_registry.py`
- Modify: `src/conexus/tests/test_framework_team_pack.py` (extend with registry tests)

- [ ] **Step 1: Write failing tests**

Append to `src/conexus/tests/test_framework_team_pack.py`:

```python
from conexus.core.team.team_registry import TeamRegistry


def test_team_registry_exposes_members(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    loader = TeamLoader(available_agents={"ana", "pm", "researcher"})
    doc = loader.load(tmp_path / "TEAM_PACK.md")
    reg = TeamRegistry(doc)
    assert reg.members == ["ana", "pm", "researcher"]
    assert reg.manager == "pm"
    assert reg.has_member("ana") is True
    assert reg.has_member("ghost") is False


def test_team_registry_edges_lookup(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    loader = TeamLoader(available_agents={"ana", "pm", "researcher"})
    reg = TeamRegistry(loader.load(tmp_path / "TEAM_PACK.md"))
    edges = reg.edges_from("pm")
    assert any(e["to"] == "researcher" for e in edges)
```

- [ ] **Step 2: Run, expect FAIL**

```
uv run pytest src/conexus/tests/test_framework_team_pack.py -v
```

- [ ] **Step 3: Implement registry**

```python
# src/conexus/core/team/team_registry.py
"""TeamRegistry — lightweight runtime view of a loaded TEAM_PACK."""
from __future__ import annotations
from typing import Any
from conexus.core.team.team_pack import TeamPackDocument


class TeamRegistry:
    def __init__(self, doc: TeamPackDocument) -> None:
        self._doc = doc

    @property
    def members(self) -> list[str]:
        return list(self._doc.frontmatter.members)

    @property
    def manager(self) -> str | None:
        return self._doc.frontmatter.manager

    @property
    def policy(self):
        return self._doc.frontmatter.policy

    @property
    def budget(self):
        return self._doc.frontmatter.budget

    def has_member(self, name: str) -> bool:
        return name in self._doc.frontmatter.members

    def edges_from(self, agent: str) -> list[dict[str, Any]]:
        return [e for e in self._doc.frontmatter.edges if e.get("from") == agent]
```

- [ ] **Step 4: Run, expect PASS**

```
uv run pytest src/conexus/tests/test_framework_team_pack.py -v
```

- [ ] **Step 5: ruff + commit**

```bash
uv run ruff check src/conexus/
git add src/conexus/core/team/team_registry.py src/conexus/tests/test_framework_team_pack.py
git commit -m "feat(phase-8.3): TeamRegistry — member/manager/edges runtime view"
```

---

## Task 4: `HandoffRouter` — Edges First, Manager LLM Fallback

**Files:**
- Create: `src/conexus/core/team/handoff_router.py`
- Create: `src/conexus/tests/test_framework_team_router.py`

- [ ] **Step 1: Write failing tests**

```python
# src/conexus/tests/test_framework_team_router.py
import pytest
from conexus.core.team.handoff import Handoff
from conexus.core.team.handoff_router import HandoffRouter
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry

PACK_MD = """---
name: t
version: 0.1.0
manager: pm
members: [ana, pm, researcher]
edges:
  - {from: pm, to: researcher, when: "task.kind == 'research'"}
  - {from: researcher, to: pm, auto: true}
budget:
  team_daily_usd: 1.0
  shares: {ana: 0.2, pm: 0.4, researcher: 0.4}
policy:
  max_hops: 3
---
"""


def _registry(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    loader = TeamLoader({"ana", "pm", "researcher"})
    return TeamRegistry(loader.load(tmp_path / "TEAM_PACK.md"))


def test_router_auto_edge_taken(tmp_path):
    router = HandoffRouter(_registry(tmp_path))
    h = Handoff(from_agent="researcher", to_agent="auto", payload={})
    target = router.route(h)
    assert target == "pm"


def test_router_when_edge_taken(tmp_path):
    router = HandoffRouter(_registry(tmp_path))
    h = Handoff(from_agent="pm", to_agent="auto", payload={"task": {"kind": "research"}})
    assert router.route(h) == "researcher"


def test_router_falls_back_to_manager(tmp_path):
    router = HandoffRouter(_registry(tmp_path))
    h = Handoff(from_agent="ana", to_agent="auto", payload={})
    assert router.route(h) == "pm"


def test_router_explicit_target_respected(tmp_path):
    router = HandoffRouter(_registry(tmp_path))
    h = Handoff(from_agent="ana", to_agent="researcher", payload={})
    assert router.route(h) == "researcher"


def test_router_unknown_target_raises(tmp_path):
    router = HandoffRouter(_registry(tmp_path))
    h = Handoff(from_agent="ana", to_agent="ghost", payload={})
    with pytest.raises(ValueError, match="unknown target"):
        router.route(h)
```

- [ ] **Step 2: Run, expect FAIL**

```
uv run pytest src/conexus/tests/test_framework_team_router.py -v
```

- [ ] **Step 3: Implement router**

```python
# src/conexus/core/team/handoff_router.py
"""HandoffRouter — resolves Handoff.to_agent.

Resolution order:
  1. If to_agent != "auto" and member exists, use it.
  2. Match `auto: true` edges from sender — first match wins.
  3. Match `when: ...` edges — first match where Python eval against payload is True.
  4. Fall back to manager.
  5. No manager → raise.
"""
from __future__ import annotations
from typing import Any
from conexus.core.team.handoff import Handoff
from conexus.core.team.team_registry import TeamRegistry


class HandoffRouter:
    def __init__(self, registry: TeamRegistry) -> None:
        self._reg = registry

    def route(self, handoff: Handoff) -> str:
        if handoff.to_agent != "auto":
            if not self._reg.has_member(handoff.to_agent):
                raise ValueError(f"unknown target: {handoff.to_agent}")
            return handoff.to_agent
        for edge in self._reg.edges_from(handoff.from_agent):
            if edge.get("auto") is True:
                return edge["to"]
            cond = edge.get("when")
            if cond and self._eval(cond, handoff.payload):
                return edge["to"]
        if self._reg.manager:
            return self._reg.manager
        raise ValueError("no edge match and no manager")

    @staticmethod
    def _eval(expr: str, payload: dict[str, Any]) -> bool:
        """Sandboxed eval — payload is the only namespace; all builtins blocked.

        Edges in TEAM_PACK.md are author-controlled (committed in repo); risk
        surface = author shooting own foot. No untrusted input reaches this.
        """
        class _Box:
            def __init__(self, d: dict[str, Any]) -> None:
                for k, v in d.items():
                    setattr(self, k, _Box(v) if isinstance(v, dict) else v)

        try:
            return bool(eval(expr, {"__builtins__": {}}, {"task": _Box(payload.get("task", {}))}))
        except Exception:
            return False
```

- [ ] **Step 4: Run, expect PASS**

```
uv run pytest src/conexus/tests/test_framework_team_router.py -v
```

- [ ] **Step 5: ruff + commit**

```bash
uv run ruff check src/conexus/
git add src/conexus/core/team/handoff_router.py src/conexus/tests/test_framework_team_router.py
git commit -m "feat(phase-8.4): HandoffRouter — explicit > auto-edge > when-edge > manager"
```

---

## Task 5: `BudgetCascader` — Pool + Shares + Three Policies

**Files:**
- Create: `src/conexus/core/team/budget_cascader.py`
- Create: `src/conexus/tests/test_framework_budget_cascader.py`

- [ ] **Step 1: Write failing tests**

```python
# src/conexus/tests/test_framework_budget_cascader.py
import pytest
from conexus.core.team.budget_cascader import BudgetCascader, BudgetPolicy, ShareExceeded


def _shares():
    return {"ana": 0.2, "pm": 0.4, "researcher": 0.4}


def test_cascader_within_share_allows():
    c = BudgetCascader(team_daily_usd=1.0, shares=_shares(), policy=BudgetPolicy.notify)
    assert c.check_and_debit("ana", 0.10) is True
    assert c.spent("ana") == pytest.approx(0.10)


def test_cascader_share_exceeded_notify_blocks():
    c = BudgetCascader(team_daily_usd=1.0, shares=_shares(), policy=BudgetPolicy.notify)
    assert c.check_and_debit("ana", 0.30) is False  # ana share = 0.20
    assert c.spent("ana") == 0.0


def test_cascader_share_exceeded_halt_member():
    c = BudgetCascader(team_daily_usd=1.0, shares=_shares(), policy=BudgetPolicy.halt_member)
    assert c.check_and_debit("ana", 0.30) is False
    with pytest.raises(ShareExceeded):
        c.check_and_debit("ana", 0.05)  # member halted — even small charge raises


def test_cascader_borrow_from_pool():
    c = BudgetCascader(team_daily_usd=1.0, shares=_shares(), policy=BudgetPolicy.borrow_from_pool)
    assert c.check_and_debit("ana", 0.30) is True  # ana exceeds own 0.20 share, borrows 0.10
    assert c.spent("ana") == pytest.approx(0.30)
    assert c.pool_remaining() == pytest.approx(0.70)
    # remaining pool can still cover within-share calls for others
    assert c.check_and_debit("pm", 0.40) is True


def test_cascader_pool_exhausted():
    c = BudgetCascader(team_daily_usd=1.0, shares=_shares(), policy=BudgetPolicy.borrow_from_pool)
    c.check_and_debit("ana", 0.20)
    c.check_and_debit("pm", 0.40)
    c.check_and_debit("researcher", 0.40)
    assert c.check_and_debit("ana", 0.01) is False  # pool empty
```

- [ ] **Step 2: Run, expect FAIL**

```
uv run pytest src/conexus/tests/test_framework_budget_cascader.py -v
```

- [ ] **Step 3: Implement cascader**

```python
# src/conexus/core/team/budget_cascader.py
"""BudgetCascader — enforces team pool + per-member shares with 3 policies.

Spec: docs/superpowers/specs/2026-04-29-conexus-framework-v2.md §1.5, §1.9.
"""
from __future__ import annotations
from enum import Enum


class BudgetPolicy(str, Enum):
    notify = "notify"               # over share → block, log, do not raise
    halt_member = "halt_member"     # over share → block, then raise on next attempt
    borrow_from_pool = "borrow_from_pool"  # over share → debit from unallocated pool


class ShareExceeded(RuntimeError):
    pass


class BudgetCascader:
    def __init__(self, team_daily_usd: float, shares: dict[str, float], policy: BudgetPolicy) -> None:
        self._pool = team_daily_usd
        self._shares = shares
        self._policy = policy
        self._spent: dict[str, float] = {m: 0.0 for m in shares}
        self._halted: set[str] = set()

    def spent(self, member: str) -> float:
        return self._spent.get(member, 0.0)

    def pool_remaining(self) -> float:
        return self._pool - sum(self._spent.values())

    def check_and_debit(self, member: str, cost: float) -> bool:
        if member in self._halted:
            raise ShareExceeded(f"{member} halted")
        share = self._shares.get(member, 0.0) * self._pool
        new_spent = self._spent.get(member, 0.0) + cost
        if new_spent <= share:
            self._spent[member] = new_spent
            return True
        # over share
        if self._policy == BudgetPolicy.notify:
            return False
        if self._policy == BudgetPolicy.halt_member:
            self._halted.add(member)
            return False
        if self._policy == BudgetPolicy.borrow_from_pool:
            if self.pool_remaining() >= cost:
                self._spent[member] = new_spent
                return True
            return False
        raise ValueError(f"unknown policy: {self._policy}")
```

- [ ] **Step 4: Run, expect PASS**

```
uv run pytest src/conexus/tests/test_framework_budget_cascader.py -v
```

- [ ] **Step 5: ruff + commit**

```bash
uv run ruff check src/conexus/
git add src/conexus/core/team/budget_cascader.py src/conexus/tests/test_framework_budget_cascader.py
git commit -m "feat(phase-8.5): BudgetCascader — pool + shares + notify/halt/borrow policies"
```

---

## Task 6: Cross-Agent TrifectaGuard — Seed Taint via `Handoff` + `trust_boundary_cleared`

**Files:**
- Modify: `src/conexus/core/trifecta/guard.py`
- Modify: `src/conexus/core/agent_handler.py`
- Create: `src/conexus/tests/test_framework_team_trifecta.py`

- [ ] **Step 1: Write failing tests**

```python
# src/conexus/tests/test_framework_team_trifecta.py
import pytest
from conexus.core.team.handoff import Handoff
from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation
from conexus.core.trifecta.tags import DataClass


def test_guard_seeded_taint_blocks_immediately():
    guard = TrifectaGuard(
        tool_tags={"wiki_write": "external_write"},
        seed_taint={DataClass.untrusted_read, DataClass.private_read},
    )
    with pytest.raises(TrifectaViolation):
        guard.check_and_record("wiki_write")


def test_guard_trust_boundary_cleared_bypasses_seed():
    guard = TrifectaGuard(
        tool_tags={"wiki_write": "external_write"},
        seed_taint={DataClass.untrusted_read, DataClass.private_read},
        trust_boundary_cleared=True,
    )
    guard.check_and_record("wiki_write")  # no raise


def test_handoff_seeds_guard_constructor():
    h = Handoff(
        from_agent="researcher",
        to_agent="pm",
        payload={},
        tags={DataClass.untrusted_read, DataClass.private_read},
    )
    guard = TrifectaGuard.from_handoff({"wiki_write": "external_write"}, h)
    with pytest.raises(TrifectaViolation):
        guard.check_and_record("wiki_write")
```

- [ ] **Step 2: Run, expect FAIL**

```
uv run pytest src/conexus/tests/test_framework_team_trifecta.py -v
```

- [ ] **Step 3: Extend `TrifectaGuard`**

Read current guard at `src/conexus/core/trifecta/guard.py`. Update constructor and add factory:

```python
# Edit src/conexus/core/trifecta/guard.py — only the class signature + new method
class TrifectaGuard:
    def __init__(
        self,
        tool_tags: dict[str, str],
        *,
        trust_boundary_cleared: bool = False,
        seed_taint: set[DataClass] | None = None,
    ) -> None:
        self._tool_tags = tool_tags
        self._trust_cleared = trust_boundary_cleared
        self._taint: set[DataClass] = set(seed_taint) if seed_taint else set()

    @classmethod
    def from_handoff(cls, tool_tags: dict[str, str], handoff: "Handoff") -> "TrifectaGuard":
        from conexus.core.team.handoff import Handoff  # local import to avoid cycle
        assert isinstance(handoff, Handoff)
        return cls(
            tool_tags,
            trust_boundary_cleared=handoff.trust_boundary_cleared,
            seed_taint=handoff.tags,
        )
```

(Keep the existing `check_and_record` method body unchanged — it already reads `self._taint` and `self._trust_cleared`.)

- [ ] **Step 4: Wire into `AgentHandlerConfig`**

In `src/conexus/core/agent_handler.py`, extend the dataclass and constructor of `TrifectaGuard`:

```python
# Add to AgentHandlerConfig dataclass
incoming_handoff: "Handoff | None" = None  # type: ignore[name-defined]

# In handle_agent_message, replace existing guard line:
# OLD: guard = TrifectaGuard(cfg.tool_tags) if cfg.tool_tags is not None else None
# NEW:
if cfg.tool_tags is None:
    guard = None
elif cfg.incoming_handoff is not None:
    guard = TrifectaGuard.from_handoff(cfg.tool_tags, cfg.incoming_handoff)
else:
    guard = TrifectaGuard(cfg.tool_tags)
```

Add `from conexus.core.team.handoff import Handoff` at top of `agent_handler.py` (or local-import inside the function — match existing pattern).

- [ ] **Step 5: Run all trifecta tests**

```
uv run pytest src/conexus/tests/test_framework_trifecta.py src/conexus/tests/test_framework_trifecta_integration.py src/conexus/tests/test_framework_team_trifecta.py -v
```
Expected: all pass (new 3 + existing 12).

- [ ] **Step 6: ruff + commit**

```bash
uv run ruff check src/conexus/
git add src/conexus/core/trifecta/guard.py src/conexus/core/agent_handler.py src/conexus/tests/test_framework_team_trifecta.py
git commit -m "feat(phase-8.6): cross-agent TrifectaGuard — seed taint via Handoff + trust_boundary_cleared"
```

---

## Task 7 [mechanical]: `conexus run team <name>` CLI

**Files:**
- Modify: `src/conexus/cli/__main__.py`
- Modify: `src/conexus/tests/test_framework_cli.py` (extend if exists; else new)

- [ ] **Step 1: Read current CLI structure**

```
uv run python -m conexus --help
```
Note existing subcommands; copy their wiring style.

- [ ] **Step 2: Write failing test**

```python
# Append to src/conexus/tests/test_framework_cli.py
def test_cli_run_team_validates_pack(tmp_path, capsys, monkeypatch):
    # Pack with unknown member should error and exit nonzero.
    pack = tmp_path / "TEAM_PACK.md"
    pack.write_text(
        "---\nname: t\nversion: 0.1.0\nmanager: pm\nmembers: [ghost]\n"
        "budget: {team_daily_usd: 1.0, shares: {ghost: 1.0}}\n---\n"
    )
    from conexus.cli.__main__ import _handle_run_team
    import argparse
    args = argparse.Namespace(pack=str(pack), available_agents="ana,pm,researcher")
    rc = _handle_run_team(args)
    assert rc != 0
    assert "unknown member" in capsys.readouterr().out.lower()
```

- [ ] **Step 3: Run, expect FAIL**

```
uv run pytest -k test_cli_run_team_validates_pack -v
```

- [ ] **Step 4: Wire subcommand**

Add to argparse setup (find existing `tag` subcommand wiring; mirror it):

```python
# In src/conexus/cli/__main__.py — add subcommand
team_p = sub.add_parser("run-team", help="Validate + run a TEAM_PACK")
team_p.add_argument("pack", help="path to TEAM_PACK.md")
team_p.add_argument("--available-agents", default="", help="comma-sep agent names available")


def _handle_run_team(args) -> int:
    from conexus.core.team.team_loader import TeamLoader
    available = set(filter(None, args.available_agents.split(",")))
    try:
        doc = TeamLoader(available).load(args.pack)
    except Exception as exc:
        print(f"team load failed: {exc}")
        return 1
    print(f"loaded team {doc.frontmatter.name}: {doc.frontmatter.members}")
    return 0
```

- [ ] **Step 5: Run, expect PASS**

```
uv run pytest -k test_cli_run_team_validates_pack -v
```

- [ ] **Step 6: ruff + commit**

```bash
uv run ruff check src/conexus/
git add src/conexus/cli/__main__.py src/conexus/tests/test_framework_cli.py
git commit -m "feat(phase-8.7): conexus run-team CLI — load + validate TEAM_PACK"
```

---

## Task 8: Reference TEAM_PACK — `agents/teams/product_team/`

**Files:**
- Create: `agents/teams/product_team/__init__.py` (empty)
- Create: `agents/teams/product_team/TEAM_PACK.md`

- [ ] **Step 1: Write the pack**

```markdown
<!-- agents/teams/product_team/TEAM_PACK.md -->
---
name: product_team
version: 0.1.0
manager: pm
members:
  - ana
  - pm
  - researcher

edges:
  - {from: ana, to: pm, when: "task.kind == 'plan'"}
  - {from: pm, to: researcher, when: "task.kind == 'research'"}
  - {from: researcher, to: pm, auto: true}

budget:
  team_daily_usd: 1.00
  shares:
    ana: 0.20
    pm: 0.40
    researcher: 0.40
  on_share_exceeded: notify

policy:
  trifecta_enforcement: strict
  max_hops: 5
  max_turns: 20
  termination_text: "DONE"

deployment:
  ana: cloud
  pm: cloud
  researcher: cloud
---
# Product team — body fragment

Three-member team. Ana fronts user requests; pm orchestrates plan + research;
researcher does external reads (web_fetch, web_search).

Default flow: user → ana → pm → researcher → pm → wiki_write.
```

- [ ] **Step 2: Validate via CLI**

```
uv run python -m conexus run-team agents/teams/product_team/TEAM_PACK.md --available-agents=ana,pm,researcher
```
Expected output: `loaded team product_team: ['ana', 'pm', 'researcher']`

- [ ] **Step 3: Commit**

```bash
git add agents/teams/product_team/
git commit -m "feat(phase-8.8): reference team pack — product_team (ana + pm + researcher)"
```

---

## Task 9: Integration Test — Full Team Flow

**Files:**
- Create: `src/conexus/tests/test_framework_team_integration.py`

- [ ] **Step 1: Write the integration test**

```python
# src/conexus/tests/test_framework_team_integration.py
"""End-to-end: ana delegates to pm; pm delegates to researcher; researcher
web_fetch (untrusted_read) + wiki_search (private_read); back to pm; pm tries
wiki_write — must be blocked by cross-agent TrifectaGuard."""

import pytest
from conexus.core.team.handoff import Handoff
from conexus.core.team.handoff_router import HandoffRouter
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry
from conexus.core.team.budget_cascader import BudgetCascader, BudgetPolicy
from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation
from conexus.core.trifecta.tags import DataClass

PACK_MD = """---
name: t
version: 0.1.0
manager: pm
members: [ana, pm, researcher]
edges:
  - {from: pm, to: researcher, when: "task.kind == 'research'"}
  - {from: researcher, to: pm, auto: true}
budget:
  team_daily_usd: 1.0
  shares: {ana: 0.2, pm: 0.4, researcher: 0.4}
  on_share_exceeded: notify
policy:
  max_hops: 5
---
"""


def test_full_team_flow_blocks_exfil(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    reg = TeamRegistry(TeamLoader({"ana", "pm", "researcher"}).load(tmp_path / "TEAM_PACK.md"))
    router = HandoffRouter(reg)
    cascader = BudgetCascader(reg.budget.team_daily_usd, reg.budget.shares, BudgetPolicy.notify)

    # ana → pm
    h1 = Handoff(from_agent="ana", to_agent="pm", payload={"task": {"kind": "plan"}})
    assert cascader.check_and_debit("pm", 0.05) is True

    # pm → researcher (kind=research routes via edge)
    h2 = Handoff(from_agent="pm", to_agent="auto", payload={"task": {"kind": "research"}})
    assert router.route(h2) == "researcher"
    assert cascader.check_and_debit("researcher", 0.05) is True

    # researcher reads web (untrusted) + wiki (private). taint accumulates.
    researcher_guard = TrifectaGuard(
        {"web_fetch": "untrusted_read", "wiki_search": "private_read", "wiki_write": "external_write"}
    )
    researcher_guard.check_and_record("web_fetch")
    researcher_guard.check_and_record("wiki_search")

    # researcher returns Handoff to pm — taint travels.
    h3 = Handoff(
        from_agent="researcher",
        to_agent="pm",
        payload={"summary": "..."},
        tags={DataClass.untrusted_read, DataClass.private_read},
        hop_count=2,
    )

    # pm receives — guard seeded with researcher's taint
    pm_guard = TrifectaGuard.from_handoff({"wiki_write": "external_write"}, h3)
    with pytest.raises(TrifectaViolation):
        pm_guard.check_and_record("wiki_write")  # blocked by cross-agent taint


def test_full_team_flow_allows_with_trust_cleared(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    reg = TeamRegistry(TeamLoader({"ana", "pm", "researcher"}).load(tmp_path / "TEAM_PACK.md"))

    h = Handoff(
        from_agent="researcher",
        to_agent="pm",
        payload={},
        tags={DataClass.untrusted_read, DataClass.private_read},
        trust_boundary_cleared=True,
    )
    pm_guard = TrifectaGuard.from_handoff({"wiki_write": "external_write"}, h)
    pm_guard.check_and_record("wiki_write")  # explicit override allowed
```

- [ ] **Step 2: Run, expect PASS**

```
uv run pytest src/conexus/tests/test_framework_team_integration.py -v
```

- [ ] **Step 3: Run full suite to confirm no regression**

```
uv run pytest
```
Expected: ≥120 pass.

- [ ] **Step 4: Commit**

```bash
git add src/conexus/tests/test_framework_team_integration.py
git commit -m "test(phase-8.9): full team flow — cross-agent trifecta block + trust-cleared bypass"
```

---

## Task 10: Wiki Sync + Brain Update

Dispatch `wiki-keeper` subagent (existing Sonnet-pinned subagent at `.claude/agents/wiki-keeper.md`).

- [ ] **Step 1: Dispatch wiki-keeper**

```
Agent({
  description: "Sync wiki to Phase 8",
  subagent_type: "wiki-keeper",
  prompt: "Phase 8 of Conexus framework just completed. New: TEAM_PACK + Handoff + HandoffRouter + BudgetCascader + cross-agent TrifectaGuard. New code lives in src/conexus/core/team/. Reference team pack at agents/teams/product_team/. Audit table at src/conexus/core/memory/handoff_audit.py. CLI added: conexus run-team. AgentRegistry now multi-backend. Sync the wiki partitions affected — likely 06-multi-agent-orchestration, 03-tools-design (Trifecta cross-agent section), 13-conexus-gap-analysis (mark Phase 8 done), 14-conexus-target-architecture (mark Phase 8 Done in roadmap). Cite file paths and line numbers."
})
```

- [ ] **Step 2: Stage + commit wiki output**

```bash
git add docs/wiki/agents-framework/
git commit -m "docs(wiki): Phase 8 sync — team primitives, BudgetCascader, cross-agent Trifecta"
```

- [ ] **Step 3: Update brain**

Update `.brain/system-pulse.md`:
- Recent Changes: prepend Phase 8 entry with task count + test count
- Current Phase: mark Phase 8 COMPLETE
- Architecture Overview: add `team/` subdir to diagram
- Key File Locations: add team module paths
- Known Risks: remove items closed by Phase 8 (multi-backend, trust_boundary_cleared, single-agent-only)

Update `.brain/roadmap.json`:
- Set `phase-8.status: completed`, `completed_at: <now>`
- Bump `summary.completed_phases` to 4
- Bump `summary.completed_tasks` accordingly

- [ ] **Step 4: Commit brain**

```bash
git add .brain/
git commit -m "chore(brain): checkpoint after Phase 8 completion"
```

---

## Task 11: Phase Review (Opus)

Dispatch Opus reviewer with full plan + git log of Phase 8 commits + spec.

**Codex pre-review gate (mandatory per `docs/dev-workflow/03-codex-validation.md`):**
Before launching Opus, dispatch `codex:codex-rescue` with the diff and spec for an independent second pass. Log verdict in `## Codex log` below.

- [ ] **Step 1: Codex pre-review**

```
Agent({
  description: "Codex pre-review Phase 8",
  subagent_type: "codex:codex-rescue",
  prompt: "Phase 8 of Conexus framework just completed (TEAM_PACK + BudgetCascader + HandoffRouter + cross-agent Trifecta). Diff: <git diff main...HEAD>. Spec: docs/superpowers/specs/2026-04-29-conexus-framework-v2.md §1.5/§1.6/§1.8/§1.9/§9. Validate: spec coverage, missing acceptance items, type-name drift, security holes in HandoffRouter._eval and TrifectaGuard.from_handoff. Return blockers + confidence rating."
})
```

- [ ] **Step 2: Log codex verdict**

Append to `## Codex log` section in this file with timestamp + prompt + verdict.

- [ ] **Step 3: Dispatch Opus reviewer**

```
Agent({
  description: "Phase 8 Opus review",
  subagent_type: "general-purpose",
  model: "opus",
  prompt: "Review Phase 8 of Conexus framework against the plan at docs/superpowers/plans/2026-04-30-phase-8-team-pack.md and the v2 spec §1.5/§1.6/§1.8/§1.9/§9. Diff: <git diff main...HEAD>. Check: every acceptance gate hit, no over-engineering vs. spec, every changed file passes /simplify, every prompt file passes /caveman:compress, no regressions in handle_agent_message hot path. Return: APPROVED / APPROVED_WITH_NOTES / BLOCKED + explicit notes per file."
})
```

- [ ] **Step 4: Address review notes**

If APPROVED_WITH_NOTES, dispatch a fix subagent (Sonnet) per note. Re-run pytest + ruff after each fix. Re-review only if notes were structural.

- [ ] **Step 5: Final per-phase quality gates**

Per `docs/dev-workflow/05-quality-gates.md`:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
git log --oneline main...HEAD  # confirm Conventional Commits format throughout
```

- [ ] **Step 6: Mark phase complete in roadmap**

Update `.brain/roadmap.json` per Task 10 if not already; ensure `current_phase_id: null` (or next phase id).

---

## Spec Acceptance — Phase 8 Subset

Per `docs/superpowers/specs/2026-04-29-conexus-framework-v2.md` §9:

| Acceptance | Plan task |
|------------|-----------|
| TEAM_PACK loads with ≥3 members | T2 + T8 |
| Manager handoff + edge routing tests pass | T4 |
| BudgetCascader pool + share with all 3 `on_share_exceeded` policies | T5 |
| Cross-agent Trifecta: web_fetch in researcher → wiki_write blocked downstream | T6 + T9 |
| Replay: frozen trace re-runs deterministically against current pack versions | **Deferred to Phase 9** — depends on Phase 1 tracer (not landed); Phase 8 ships handoff_audit table to make replay implementation straightforward later |
| `pip install conexus` lands a working CLI | Already shipped Phase 6 |
| MCPProducer responds to Claude Code | **Deferred to Phase 9** — net-new producer/server work; orthogonal to TEAM_PACK; Phase 8 must not block on producer surface |

### Phase 8 Scope Decision (recorded 2026-04-30, post-codex)

Codex pre-phase flagged §9 replay + §9 MCPProducer as gaps. Decision: **narrow Phase 8 scope** to the team-coordination subset of §9 (TEAM_PACK, handoff, BudgetCascader, cross-agent Trifecta). Replay + MCPProducer move to **Phase 9**.

Why: Both are net-new subsystems requiring Phase 1 (tracer) and net-new MCP server scaffolding respectively — bundling them inflates Phase 8 to ~20 tasks with two unrelated risk surfaces. Senior-engineer practice: ship one coherent capability per phase.

Phase 9 plan must explicitly land both gates before v2 spec is fully accepted.

### Items Deferred to Phase 9 (post-pre-review codex audit, 2026-04-30)

Phase 8 lands the team-coordination *substrate* (typed envelope, deterministic router, audit, budget pool, cross-agent taint). The runtime *semantics* — wiring the substrate into the agent loop — moves to Phase 9 as part of multi-agent runtime activation:

- **`delegate_to_<agent>` LLM tool** (codex B-4) — spec §1.6 line ~159: an LLM-emitted tool that hands the loop to a sibling agent. Phase 8 ships `Handoff` Pydantic + `HandoffRouter`; Phase 9 wires LLM tool emission + agent loop yield/resume.
- **`context_mode` per-edge** (B-5) — `Handoff.context_mode` field stores the value; per-edge transcript trimming logic lives in Phase 9 runtime.
- **`return_on` stack-return** (B-6) — Phase 8 stores the field; Phase 9 implements the call-stack pop semantics.
- **`max_parallel_members`** (B-9) — `TeamPolicy` model lacks this; Phase 9 adds it once parallel scheduling is wired.
- **Trust-boundary clear as auditable operation** (B-2) — Phase 8 uses raw `bool`; Phase 9 introduces a logged `TrifectaGuard.clear_boundary(reason)` operation.
- **Pip-installable TEAM_PACK smoke test** (B-7) and **`deployment` field round-trip test** (B-8) — Phase 9 adds with the multi-host activation work.
- **`policy.termination_text` consumed by agent loop** — Phase 8 parses the field; Phase 9 wires the loop check (`reply.endswith(termination_text)` → halt) once the multi-agent loop is active.

Spec §9 acceptance for `delegate_to_<agent>` flow + §1.6 stack-return + §1.9 max_parallel_members must all land in Phase 9 before v2 acceptance.

---

## Codex log

| Date (UTC) | Trigger | Prompt summary | Verdict | Action |
|------------|---------|----------------|---------|--------|
| 2026-04-30 | Pre-phase plan validation | This plan + v2 spec, decision matrix per dev-workflow §03 | **changes-needed** (3 issues) | Issue 3 fixed: `list_tools()` added to ToolBackend ABC, Python + Mcp backends impl, registry routes via manifest. Issues 1+2 fixed: replay + MCPProducer formally deferred to Phase 9 (scope decision recorded in §Phase 8 Scope Decision). |
| 2026-04-30 | Pre-phase-review diff audit (post-T10) | Diff `d476101^..HEAD` + spec §1.5–§1.9 | **changes-needed** — 11 blockers, 8/10 confidence | **B-1 fixed (commit aa717aa)**: HandoffRouter `_eval` replaced with whitelisted AST walker; `__class__`/`__subclasses__` traversal blocked; tests `test_router_eval_blocks_dunder_traversal` + `_blocks_function_calls`. **B-3 fixed (commit aa717aa)**: HandoffRouter accepts sqlite conn; writes audit row per route with outcome ∈ {routed, unknown_target, no_match}; tests `test_router_writes_audit_row` + `_on_unknown_target`. **B-2/B-4/B-5/B-6/B-9 deferred to Phase 9** (runtime semantics — `delegate_to_<agent>` LLM tool, `context_mode` per-edge, `return_on` stack-return, `max_parallel_members`, trust-boundary clear method); recorded in §Phase 8 Scope Decision. **B-7 (pip-install test) + B-8 (deployment field test)**: low-risk, defer to Phase 9 with a smoke test. **B-10/B-11**: already deferred per pre-phase scope decision. |

---

## Self-Review Checklist (run before Codex pre-phase dispatch)

1. **Spec coverage:**
   - §1.2 solo vs team opt-in → T7 (CLI), T11 (acceptance)
   - §1.5 TEAM_PACK format → T2 + T8
   - §1.6 Handoff mechanics (versioned, hop, return_on, context_mode) → T1
   - §1.8 cross-agent TrifectaGuard + trust_boundary_cleared → T6
   - §1.9 BudgetCascader pool + 3 policies → T5
   - HandoffRouter edges + manager fallback → T4
   - Audit log → T1 (handoff_audit table)
   - AgentRegistry multi-backend prep → T0

2. **Placeholder scan:** none. Every task has full code blocks. No "TBD". Codex pre-phase verdict applied 2026-04-30 (issues 1–3 resolved).

3. **Type consistency:**
   - `Handoff` shape used in T1, T4, T6, T9 — same field set everywhere.
   - `BudgetPolicy` enum values match TEAM_PACK YAML literals.
   - `TeamRegistry.budget.shares` accessed in T9; matches `TeamBudget.shares` from T2.
   - `TrifectaGuard.from_handoff` signature `(tool_tags, handoff)` consistent T6 + T9.
   - `register_backend(agent, backend)` signature unchanged from Phase 7; T0 only adds list semantics.
