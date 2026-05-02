# Conexus Framework v2 — Spec (2026-04-29)

> **Status:** SPEC. Supersedes `2026-04-24-conexus-framework-v2-draft.md` (kept as historical record).
> **Brand:** "You direct. Agents execute."
> **Tagline:** Build one agent or a full team — each with role, tools, budget, memory.

## 0. Why v2

Conexus v1 (Ana + Pesquisador on Fly.io + Telegram) proved single-agent works.
Goal of v2 = **let teams of agents collaborate** so the operator can orchestrate
specialised roles instead of stretching one agent across every job. Side-goal =
make the framework distributable so others can ship agents on the same kernel.

This spec reconciles three earlier inputs:

1. `docs/wiki/agents-framework/14-conexus-target-architecture.md` (kernel posture, conservative)
2. `docs/specs/2026-04-16-conexus-framework-design.md` (single + team + MCP + Trifecta)
3. `docs/superpowers/specs/2026-04-24-conexus-framework-v2-draft.md` (full ambition draft)

The 2026-04-16 design wins on shape. v2 draft wins on packaging primitives.
Target-arch wins on kernel discipline (loud failures, single tool loop, cache
awareness). v2 spec keeps each where it earns its keep and **cuts** what is
premature for a solo operator with two production agents.

---

## 1. Locked Decisions

### 1.1 Framework / consumer split

Conexus = **library** (pip package). Agents = **consumers**.

```
conexus/                           # framework pkg, pip-installable
  core/        kernel: handle_agent_message, registries, budget, tracer
  skills/      SkillLoader, SkillRegistry, SKILL_PACK format
  team/        TeamLoader, TeamRegistry, BudgetCascader, TrifectaGuard
  mcp/         MCPProducer (expose), MCPConsumer (consume)
  cli/         `conexus run agent <name>`, `conexus run team <name>`

agents/                            # consumer code (today's repo evolves to this shape)
  ana/         SKILL.md, tools.py, jobs.py
  pesquisador/ SKILL.md, tools.py, jobs.py
  teams/       (future) TEAM_PACK.md files
```

Ana + Pesquisador are **reference consumers**, not framework code. Validates
dogfooding: any external user installs `conexus` the same way Leandro does.

Hosting + transport (Fly, Telegram) = consumer concerns. Framework is
deployment-agnostic. CLI / MCP entry points are first-class; Telegram is one
adapter among many.

### 1.2 Solo agent = default. Team = opt-in.

```bash
conexus run agent ana                # solo, no team primitives loaded
conexus run team product_team        # team primitives active
```

Solo path runs:
- one `handle_agent_message` loop
- one `AgentRegistry`
- one `SkillRegistry`
- TrifectaGuard (always on — security)
- per-agent BudgetCap (always on)

Team path adds:
- `TeamRegistry` (members, edges, manager)
- `BudgetCascader` (pool + shares)
- cross-agent TrifectaGuard taint propagation
- handoff (`delegate_to_<agent>`)

Solo agent never pays for team machinery.

### 1.3 SKILL_PACK format

Pip-installable Python package. Ships:

- `SKILL_PACK.md` — YAML frontmatter + prompt-fragment body
- Optional `tools.py` — in-proc Python tools (decorator: `@tool`)
- Optional `mcp.json` — external MCP server config (stdio or http)
- Optional `policy.yaml` — default tags, budget hints

Frontmatter:

```yaml
name: kanban
version: 0.1.0
backend: python              # python | mcp-stdio | mcp-http
capabilities: [ticket_create, ticket_list, ticket_update]
data_classes:                # for TrifectaGuard; framework auto-tags by heuristic if omitted
  ticket_create: external_write
  ticket_list:   private_read
budget_hint_usd: 0.01
prompts:
  - fragments/kanban_usage.md   # injected into agent system prompt at load
```

Agent SKILL.md references skills by name + version:

```yaml
skills:
  - kanban@0.1.0
  - wiki@1.2.0
  - web-search@0.3.0
```

### 1.4 Backend abstraction (unified)

Framework treats three backends uniformly. Author writes once; framework dispatches:

| Backend       | Process        | Use when                                         |
|---------------|----------------|--------------------------------------------------|
| `python`      | in-process     | hot-path tools, our SQLite/wiki, native code     |
| `mcp-stdio`   | subprocess     | third-party MCP server (filesystem, github, etc) |
| `mcp-http`    | remote HTTP    | hosted MCP server (Linear, Stripe, fetch)        |

Same `AgentRegistry.execute_tool(name, args)` API regardless of backend.

### 1.5 TEAM_PACK format

Pip-installable. Hybrid topology (graph edges + manager handoff fallback).

```yaml
# TEAM_PACK.md frontmatter
name: product_team
version: 0.1.0
manager: pm                  # null → swarm; named → supervisor
members:
  - ana
  - pm
  - architect
  - researcher
  - scribe

edges:                       # deterministic when matched, else manager LLM decides
  - { from: pm, to: architect, when: "task.kind == 'design'" }
  - { from: architect, to: scribe, auto: true }

budget:
  team_daily_usd: 1.00
  shares: { pm: 0.2, architect: 0.3, researcher: 0.3, scribe: 0.2 }
  on_share_exceeded: notify  # notify | halt_member | borrow_from_pool

policy:
  trifecta_enforcement: strict   # strict | warn | off
  max_hops: 5
  max_turns: 20
  termination_text: "DONE"

deployment:                  # consumer concern; framework records but does not enforce
  ana: cloud
  pm:  cloud
```

### 1.6 Delegation mechanics

- **Default = tool-call handoff.** LLM emits `delegate_to_<agent>(payload)`. New agent owns the loop.
- **Edges layer on top.** Deterministic routing when `edges:` block matches.
- **Context pass.** Per edge: `full | last_message | summary` (default `summary`).
- **Return semantics.** Fire-and-forget by default. `return_on: <condition>` for stack-return.
- **Hop counter.** `Handoff.hop_count`; aborts at `max_hops` with audit row.

Payload is typed Pydantic, versioned (`schema_version: "1"`).

### 1.7 MCP — both directions

**Consumer (Conexus as host):** `mcp_servers:` block in `SKILL_PACK.md` connects
remote MCP servers. Tools land in `AgentRegistry` under namespaced names
(`github.create_issue`).

**Producer (Conexus as MCP server):** ships `conexus-mcp` entry point that
exposes Conexus capabilities to external MCP clients (Claude Code, Cursor, IDE).

Producer surface (v2 scope):

| Primitive | Surface                                                          |
|-----------|------------------------------------------------------------------|
| Resources | `wiki://{agent}/{path}`, `traces://{agent}/{trace_id}` (if Phase 1 tracer landed) |
| Tools     | `wiki_search`, `wiki_read`, `delegate_to_<agent>`, `log_session` |
| Prompts   | `daily_brief`, `start_research`                                  |

Transport: **stdio + Streamable HTTP**. Auth: **bearer token + scope** for v2.
OAuth 2.1 + Dynamic Client Registration deferred to Phase 7.

### 1.8 TrifectaGuard — deterministic, no LLM

Static taint check, runtime cost = ~5 µs per tool call.

**Tags.** Every tool declares one `data_class`:

| Tag              | Examples                                                           |
|------------------|--------------------------------------------------------------------|
| `untrusted_read` | `web_fetch`, `web_search`, `read_email`, `read_dm`                 |
| `private_read`   | `wiki_read`, `wiki_search`, `memory_get`, `db_read`, `calendar_list` |
| `external_write` | `send_telegram`, `wiki_write`, `git_push`, `delete_*`, `post_*`    |
| `safe`           | pure compute, deterministic transforms                             |

**Auto-tag heuristic** at skill load: regex match on tool name + signature.
Author override in `SKILL_PACK.md` `data_classes:` map. **Untagged + no
heuristic match → load fails loud.**

**Rule.** Per-turn state tracks accumulated tags. If turn contains
`{untrusted_read, private_read}` AND tool with `external_write` is requested →
**block**, audit, notify operator. Cross-agent: tags travel in `Handoff` payload
and seed receiver's turn state.

**Override.** Explicit `trust_boundary: cleared` flag in handoff or per-call —
operator must set; default false. Logged.

### 1.9 Guardrails — layered

Each layer opt-in (except Trifecta + audit). Independent failure modes.

| Layer    | Limits                                                                  | Config                              |
|----------|-------------------------------------------------------------------------|-------------------------------------|
| Tool     | rate limit, retry budget, timeout                                       | `SKILL_PACK.md` frontmatter         |
| Agent    | daily $, max turns/trace, max tool calls/turn, skill allow-list         | `agents/<x>/SKILL.md`               |
| Team     | pool $, max parallel members, max hops, termination text, share enforce | `TEAM_PACK.md`                      |
| System   | global $ kill switch, per-day cap across all agents, emergency shutdown | env / `conexus.toml`                |
| Trifecta | tag-based block (deterministic, always on)                              | per-tool `data_class`               |
| Audit    | every tool call + handoff logged, replayable                            | always on (`tool_audit`, `handoff_audit`) |

### 1.10 Observability

Phase 1 of target arch lands first: `trace_id` ContextVar, `Tracer` (SQLite
backend, optional Langfuse), `tool_audit` table, `trace_checkpoints` table.

OTEL bridge across MCP boundary (carrying `traceparent` from external client to
Conexus internal graph) **deferred to Phase 7**. Local tracer is enough for solo
operator.

---

## 2. Scope cuts (vs 2026-04-24 draft)

Removed from v2 because premature for current scale + complexity budget:

| Cut                                            | Reason                                                                                  | Re-evaluation gate                                  |
|------------------------------------------------|-----------------------------------------------------------------------------------------|-----------------------------------------------------|
| `tickets://` MCP resource                      | No ticket store exists. PM agent + kanban skill must ship first.                       | After PM agent + kanban skill ship                  |
| `specs://` MCP resource                        | Specs already live in `docs/`. Use `wiki://docs/specs/...`.                            | Never — wiki:// covers it                           |
| Streaming delegation (`notifications/progress`)| Telegram doesn't stream. No MCP client waits >60s today.                               | First delegate that trips 60s wall                  |
| Verifier role (MAST-FC3)                       | Cost ≈ 2× per handoff. Hypothetical failure mode. Deterministic guards cover 80%.      | After 3 real bad-handoff incidents                  |
| OAuth 2.1 + Dynamic Client Registration        | Bearer + scope sufficient for solo + small team. DCR interop still rough industry-wide. | First external multi-tenant deploy                  |
| OTEL `traceparent` MCP bridge                  | Local SQLite tracer covers debug needs.                                                | Cross-system trace becomes load-bearing             |

---

## 3. Architecture

```
┌─ conexus (framework, pip pkg) ─────────────────────────────────────┐
│                                                                     │
│  CLI ──► loader ──► AgentRegistry ──► handle_agent_message          │
│                          │                                          │
│                          ├─ SkillRegistry (python | mcp-stdio | http)│
│                          ├─ TrifectaGuard (always on)               │
│                          ├─ BudgetCap (always on)                   │
│                          ├─ Tracer (always on, SQLite)              │
│                          │                                          │
│           team-mode only ▼                                          │
│                    TeamRegistry                                     │
│                          ├─ BudgetCascader                          │
│                          ├─ HandoffRouter (edges + manager)         │
│                          └─ cross-agent TrifectaGuard               │
│                                                                     │
│  MCPProducer ── Streamable HTTP + stdio                             │
│    ├─ wiki://, traces:// resources                                  │
│    ├─ wiki_search, delegate_to_*, log_session tools                 │
│    └─ daily_brief, start_research prompts                           │
└─────────────────────────────────────────────────────────────────────┘
                ▲
                │ stdio | HTTP+bearer
                │
┌─ consumers ───┴────────────────────────────────────────────────────┐
│  Telegram bot adapter (current Ana + Pesquisador entry)             │
│  Claude Code / Cursor (via MCP producer)                            │
│  Future: REST API, web UI, voice                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Components

| Component         | New / Evolves | Owner               |
|-------------------|---------------|---------------------|
| `SkillLoader`     | evolves       | resolves `skills:` list, picks backend, hydrates prompts |
| `SkillRegistry`   | new           | live skill instances per agent, dispatches `call(skill, tool, args)` |
| `TeamLoader`      | new           | parses TEAM_PACK.md, validates members exist, wires edges |
| `TeamRegistry`    | new           | runtime team state, manager handle, share accounting |
| `BudgetCascader`  | new           | extends `CapChecker`. Pool + share enforcement. |
| `TrifectaGuard`   | new           | deterministic taint check, tags travel via `Handoff` |
| `HandoffRouter`   | new           | edges first, then manager LLM, hop counter, audit |
| `MCPProducer`     | new           | FastMCP server, bearer auth, exposes wiki/tools/prompts |
| `MCPConsumer`     | evolves       | extends current MCP adapter draft; per-server allow-list |
| `Tracer`          | new (Phase 1) | SQLite backend; ContextVar `trace_id`; OTEL conventions  |

---

## 5. Data flow examples

**Solo (today's Ana, post-migration):**
```
Telegram msg → ana adapter → handle_agent_message
  → SkillRegistry resolves wiki@1.2.0
  → TrifectaGuard tags wiki_search = private_read
  → LLM call → tool dispatch → reply
```

**Team:**
```
Telegram msg → ana → delegate_to_pm
  → HandoffRouter checks edges (pm.in: ana → ok)
  → BudgetCascader debits pm share
  → pm loop → delegate_to_researcher (tagged untrusted_read after web_fetch)
  → TrifectaGuard blocks researcher's external_write attempt
  → researcher returns summary → pm composes ticket → wiki_write
```

**External MCP client:**
```
Claude Code: @mention wiki://ana/calendar_facts
  → MCPProducer authn (bearer) → resource read
  → returns markdown
Claude Code: log_session(commits=[abc123], notes="...")
  → MCPProducer → wiki_write under ana namespace
```

---

## 6. Error handling

- Tool error → `{"error": ...}` JSON string (current invariant). MCP wraps `isError: true`.
- Trifecta violation → abort turn, audit row, Telegram alert, MCP `isError`.
- Budget cascade exceeded → per-share `on_share_exceeded` policy: `notify`, `halt_member`, `borrow_from_pool`.
- Handoff loop / max_hops → abort with full path in audit.
- Skill load fail (untagged tool, missing dep) → loud at startup, never runtime fallback.

---

## 7. Testing

- **Unit:** SkillLoader backend dispatch, BudgetCascader accounting, TrifectaGuard taint propagation including cross-agent, HandoffRouter edge resolution.
- **Integration:** TEAM_PACK load + run against fake LLM; MCP producer against MCP spec conformance suite.
- **E2E:** Telegram → solo Ana, Telegram → team handoff, Claude Code MCP client → Conexus producer round-trip.
- **Replay:** frozen trajectories from `trace_checkpoints` re-run against updated SKILL_PACK / TEAM_PACK for regression.

---

## 8. Phasing

Execute target-arch Phases 0-5 first (kernel work), then v2 team primitives.

| Phase | Block                                                                   | Effort |
|-------|-------------------------------------------------------------------------|--------|
| 0     | Bug-fix sprint (target arch §7 Phase 0)                                 | 5d     |
| 1     | Observability + evals foundation (target arch §7 Phase 1)               | 8d     |
| 2     | Memory upgrade (target arch §7 Phase 2)                                 | 10d    |
| 3     | Cost optimisation (target arch §7 Phase 3)                              | 5d     |
| 4     | Tools evolution + MCP consumer (target arch §7 Phase 4)                 | 7d     |
| 5     | Multi-agent scaffold + Handoff primitive (target arch §7 Phase 5)       | 4d     |
| **6** | **Framework / consumer split — Ana + Pesq become consumers**            | 5d     |
| **7** | **SKILL_PACK + TrifectaGuard + per-agent BudgetCap**                    | 8d     |
| **8** | **TEAM_PACK + BudgetCascader + HandoffRouter + cross-agent Trifecta**   | 10d    |
| **9** | **MCPProducer (bearer auth) — expose Conexus to Claude Code / Cursor**  | 6d     |
| 10+   | Deferred: streaming delegation, verifier, OAuth 2.1, OTEL bridge       | tbd    |

Phases 6-9 = v2 net-new. Phases 0-5 reuse target-arch plan unchanged.

---

## 9. Acceptance — "v2 framework complete"

- [ ] `pip install conexus` lands a working CLI; `conexus run agent ana` works.
- [ ] Ana + Pesquisador run as consumers (own repo or `agents/` sub-pkg).
- [ ] SKILL_PACK format parses; in-proc + mcp-stdio + mcp-http backends all dispatch via same registry.
- [ ] TrifectaGuard blocks the canned exfil scenario; every tool tagged or load fails.
- [ ] TEAM_PACK loads with ≥ 3 members; manager handoff + edge routing both pass tests.
- [ ] BudgetCascader enforces team pool + per-member share with `on_share_exceeded` policies.
- [ ] MCPProducer responds to Claude Code; bearer auth round-trip works; wiki:// resource readable.
- [ ] Cross-agent Trifecta taint: web_fetch in researcher → wiki_write blocked downstream in pm.
- [ ] Replay: frozen trace re-runs deterministically against current pack versions.

---

## 10. Open risks (not yet mitigated)

1. **BudgetCascader accounting under parallel delegation + retries** — share-split heuristic may undercount. Track via integration test with deliberate parallel + retry harness.
2. **TrifectaGuard false positives** — legitimate flows blocked. Mitigation: `trust_boundary: cleared` escape hatch + per-block audit row to tune heuristic over time.
3. **Double manifest cognitive load (SKILL_PACK + TEAM_PACK)** — bad docs = adoption killed. Mitigation: single example team-pack repo + `conexus init` scaffold.
4. **MCP tool timeout vs long delegation** — Claude Code default 60s. Bump client-side; streaming progress is Phase 10.
5. **Cloud cannot push to laptop** — cloud-deployed team is pull-only from local MCP perspective. Acceptable for v2 (cloud Conexus = source of truth; laptop = consumer).

---

## 11. Out of scope (v2)

- Verifier role (MAST-FC3 mitigation) — Phase 10+.
- Streaming delegation via `notifications/progress` — Phase 10+.
- OAuth 2.1 + DCR — Phase 10+.
- Signed skill marketplace — after 3+ reference packs ship.
- Visual team-builder UI — see `docs/wiki/agents-framework/15-future-vision.md`.
- A2A federation across organisations — Phase 11+.
- Multi-tenant isolation — Metal Shopping consumer concern, not framework.
- sqlite-vec memory tier — kicks in only when corpus > 200 (per target arch §3 phasing).

---

*Spec is load-bearing. Implementation that contradicts must update this doc first or be rejected. Last revised 2026-04-29.*
