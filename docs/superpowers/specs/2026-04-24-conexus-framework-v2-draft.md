# Conexus Framework v2 — Design Draft (2026-04-24)

> **Status:** ARCHIVED — SUPERSEDED by [`2026-04-29-conexus-framework-v2.md`](2026-04-29-conexus-framework-v2.md) on 2026-04-29.
>
> Kept as historical record. Decisions in this draft were reviewed against
> `docs/wiki/agents-framework/14-conexus-target-architecture.md` and trimmed.
> The 04-29 spec drops: `tickets://` + `specs://` MCP resources, streaming
> delegation, verifier role, OAuth 2.1 + DCR, OTEL bridge across MCP boundary.
> The 04-29 spec keeps: SKILL_PACK + TEAM_PACK formats, unified backend
> abstraction, MCP producer + consumer (bearer auth), deterministic
> TrifectaGuard, layered guardrails, framework/consumer split, solo-default +
> team-opt-in modes.
>
> See `docs/wiki/agents-framework/15-future-vision.md` for items deferred
> beyond v2 (marketplace, visual UI, A2A, signed packs).
>
> Original draft status (do not act on): DRAFT for adversarial review.
> Decisions locked in brainstorm; not yet implemented.

## Goal

Evolve Conexus from "one-agent-per-SKILL.md runtime" (current production) into a **generic agent-team framework** with:

- declarative agent + team definitions
- distributable skill + team packages (pip)
- cloud+local hybrid deployment per team member
- bidirectional MCP bridge (consumer + producer)
- cost + policy cascade across teams
- production-grade observability (OTEL)

Framework must support personal-agent use (today: Ana + Pesquisador on Fly.io + Telegram) **and** multi-tenant team-pack distribution without fork.

---

## Locked Decisions

### 1. Plugin shape — (c) unified backend abstraction

SKILL_PACK = declarative manifest + authoring shape; framework treats three backends uniformly:

- **Python in-proc** — `@tool` decorator on methods (current `Tools` class lineage)
- **MCP subprocess** — stdio MCP server (language-agnostic, isolated)
- **MCP HTTP** — remote MCP server (third-party, hosted)

Author writes once in SKILL_PACK.md; framework picks backend at load. Follows Claude Agent SDK pattern (decorator = in-proc MCP server).

### 2. SKILL_PACK.md format

Pip-installable Python package. Ships:

- `SKILL_PACK.md` — YAML frontmatter + prompt-fragment body
- Optional `tools.py` — in-proc Python tools
- Optional `mcp.json` — external MCP server config
- Optional `policy.yaml` — default trifecta tags, budget hints

Frontmatter:

```yaml
name: kanban
version: 0.1.0
backend: python | mcp-stdio | mcp-http
capabilities: [ticket_create, ticket_list, ticket_update]
data_classes:
  ticket_create: external_write
  ticket_list: private_read
budget_hint_usd: 0.01  # per-call advisory
prompts:
  - fragments/kanban_usage.md  # injected into agent system prompt
```

Agent SKILL.md references by name + version:

```yaml
skills:
  - kanban@0.1.0
  - wiki@1.2.0
  - web-search@0.3.0
```

### 3. MCP producer (Conexus exposes self)

Streamable HTTP + OAuth 2.1 (PKCE + Dynamic Client Registration, RFC 7591). Stdio fallback for local.

Primitive mapping:

| MCP primitive | Conexus surface |
|---|---|
| Resources | `wiki://{agent}/{slug}`, `tickets://{project}/{id}`, `specs://{project}/{ticket_id}`, `traces://{agent}/{session_id}` |
| Tools | `search_wiki`, `create_ticket`, `update_ticket`, `delegate_to_<agent>`, `log_coding_session` |
| Prompts | `start_research`, `weekly_planning`, `sync_coding_session` |

**Innovation bets committed:**

- **A. Streaming delegation.** External MCP client calls `delegate_to_<agent>` → MCP `notifications/progress` events stream sub-agent work back to client. Uses MCP spec `notifications/progress`. No framework ships this.
- **B. OAuth-scoped resource namespaces.** Per-agent wiki scopes: `wiki:ana:read`, `wiki:pesq:write`, `tickets:metalshopping:*`. Spec-supported, unshipped industry-wide.
- **C. OTEL trace context bridge.** `traceparent` header from external MCP client → Conexus internal agent graph → back to client. Full trace across cloud/local boundary.

### 4. Team abstraction — TEAM_PACK.md

Hybrid topology (graph + handoff). Pip-installable.

```yaml
# TEAM_PACK.md frontmatter
name: product_team
version: 0.1.0
topology: hybrid
manager: pm
members:
  - ana        # user-facing
  - architect
  - researcher
  - scribe
  - verifier   # optional MAST-FC3 mitigation

edges:  # deterministic routing when set; else manager LLM handoff
  - { from: pm, to: architect, when: "task.kind == 'design'" }
  - { from: architect, to: scribe, auto: true }

budget:
  team_daily_usd: 1.00
  shares: { pm: 0.2, architect: 0.3, researcher: 0.3, scribe: 0.15, verifier: 0.05 }

policy:
  trifecta_enforcement: strict  # cross-agent taint tracking

termination:
  max_turns: 20
  on_text: "DONE"

deployment:
  ana: cloud
  pm: cloud
  architect: cloud
  researcher: cloud
  scribe: cloud
  # future: impl_analyzer: local
```

**Innovation bets committed:**

1. **TEAM_PACK.md as pip-installable unit.** `pip install conexus-team-research` → 3 pre-wired agents + budgets + policy. No framework ships this.
2. **Cascading budget** with declared shares. `team_daily_usd` splits per `shares:` map per member.
3. **Cross-agent trifecta enforcement.** Tags travel with skill pack. Runtime tracks taint across `delegate_to`. Willison's lethal trifecta — first framework to enforce cross-agent.
4. **Hybrid per-member deployment.** `deployment:` block declares cloud vs local per agent. Cross-boundary = MCP bridge (#3 above).
5. **Verifier role as first-class primitive.** Optional team member reviews manager handoffs before firing. Mitigates MAST-FC3 (task verification failures).

### 5. Delegation mechanics

- **Tool-call handoff** = default. LLM emits `delegate_to_<agent>` tool; new agent owns loop.
- **Graph edges** = layered on top via `edges:` block for deterministic flows.
- **Context pass** = configurable per edge: `full | last_message | summary`.
- **Return semantics** = fire-and-forget default; `return_on: <condition>` for stack return.

---

## Architecture

```
┌─ Fly.io (cloud) ───────────────────────────────────┐
│                                                     │
│  Telegram bots ── handler closures                  │
│         │                                           │
│         ▼                                           │
│  handle_agent_message (unchanged core loop)         │
│         │                                           │
│    ┌────┴────┐                                      │
│    ▼         ▼                                      │
│  AgentRegistry   SkillRegistry (new)                │
│    │               │                                │
│    │               ├─ Python in-proc tools          │
│    │               ├─ MCP stdio subprocess          │
│    │               └─ MCP HTTP client               │
│    ▼                                                │
│  TeamRegistry (new)                                 │
│    │                                                │
│    ├─ BudgetCascader (new)                          │
│    ├─ TrifectaGuard (new, cross-agent taint)        │
│    └─ VerifierHook (new, optional)                  │
│                                                     │
│  MCP Producer (new) ─── Streamable HTTP + OAuth 2.1 │
│    │                                                │
│    ├─ Resources: wiki://, tickets://, traces://     │
│    ├─ Tools: search_wiki, delegate_to_*, ...        │
│    └─ Prompts: start_research, weekly_planning      │
│                                                     │
│  OTEL exporter (new)                                │
│                                                     │
└─────────────────────────────────────────────────────┘
              ▲
              │ MCP Streamable HTTP + OAuth 2.1
              │
┌─ Laptop ────┴───────────────────────────────────────┐
│                                                     │
│  Claude Code Desktop ─ MCP client                   │
│    ├─ reads wiki:// resources (@-mention)           │
│    ├─ reads tickets:// resources                    │
│    ├─ calls delegate_to_pm (streaming progress)     │
│    └─ calls log_coding_session on wrap             │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Components

- **SkillLoader** (extends current `skill_loader.py`) — resolves `skills: [...]` list to backend-specific loaders; hydrates prompt fragments.
- **SkillRegistry** — new. Holds live skill instances per agent; dispatches `call(skill_name, tool_name, args)` regardless of backend.
- **TeamRegistry** — new. Loads TEAM_PACK.md; wires members, edges, termination, budget cascade, policy.
- **BudgetCascader** — new. Extends current `CapChecker`. Tracks team_daily_usd pool; per-member share enforcement; cross-member accounting.
- **TrifectaGuard** — new. Tags propagate from skill pack → tool call → turn state. Cross-`delegate_to` taint tracking. Aborts turn on trifecta violation.
- **VerifierHook** — new. Optional team member; runs before manager handoff fires; may reject/modify.
- **MCPProducer** — new. Streamable HTTP server; OAuth 2.1 + DCR; exposes resources/tools/prompts per locked mapping; emits `notifications/progress` during delegations.
- **OTELExporter** — new. `traceparent` ingest from MCP; span creation per agent turn; propagation through delegate_to; emit back in `content` of MCP responses.

## Data Flow — representative

User sends Telegram idea → Ana → `delegate_to_pm` (tool call) → PM → `create_ticket` → ticket written to SQLite + wiki git commit.

Later: Claude Code Desktop opens project → MCP connect Fly → OAuth flow → `@mention tickets://metalshopping/T-42` → fetches resource → user implements → `log_coding_session(project=metalshopping, commits=[abc123], notes="...")` → MCP tool call → Conexus updates ticket + wiki.

Cross-agent: Ana → delegate_to_researcher (tagged untrusted_read after web_fetch) → researcher returns summary → TrifectaGuard blocks any same-turn external_write carrying tainted content.

## Error Handling

- Tool errors: `AgentRegistry.execute_tool` returns `{"error": ...}` string (current invariant). MCP wraps as `isError: true` content block.
- Budget cascade exceeded: team-level halt or notify per `on_exceed` (per-member override allowed).
- Trifecta violation: abort turn; log incident; Telegram warning to operator; MCP response = content block with violation detail.
- MCP session loss: reconnect on client side; server stateless per session-id for idempotent tools, sticky for streaming deliveries.
- Verifier rejection: return to manager with rejection reason for retry; bounded retries (default 2).

## Testing Approach

- Unit: SkillLoader backend dispatch, BudgetCascader accounting, TrifectaGuard taint propagation, VerifierHook reject/accept.
- Integration: TEAM_PACK.md load + run against fake LLM; MCP producer against MCP spec conformance test; OAuth DCR flow against Claude Code Desktop.
- E2E: Telegram → cloud team → delegate_to → progress stream to MCP client.
- Replay: Phase 2 — frozen trajectory re-run against updated SKILL_PACK/TEAM_PACK for regression.

## Out of Scope (v2)

- AutoResearch loop (Phase 2+ per earlier spec).
- Voice-in / Whisper integration.
- Signed skill marketplace (build after 3+ reference packs exist).
- sqlite-vec memory tier (current corpus < 200, BM25 tier sufficient).
- Multi-tenant isolation per deployment (deferred to Metal Shopping fork).

---

## Open Risks (flagged by proposer, not yet mitigated)

1. **Cascading budget accounting** under parallel delegation + retries = hard accounting problem. Letta/Magentic-One have not solved. Simple share-split may undercount.
2. **Trifecta false positives.** Legitimate flows blocked = user frustration. Needs explicit `trust_boundary: cleared` escape hatch.
3. **Team-pack marketplace chicken-egg.** Bootstrap by shipping 3 reference packs (wiki, research, engineering-adjunct) internally.
4. **Double manifest (SKILL_PACK + TEAM_PACK)** = cognitive cost; bad docs = adoption killed.
5. **OTEL + OAuth + MCP stack** = operational weight; personal single-user overkill; must be opt-in with simple default.
6. **MCP tool timeout** (Claude Code default 60s) collides with long delegations — must emit `notifications/progress` or bump timeout.
7. **OAuth Dynamic Client Registration** interop known-rough across providers (Cloudflare hit issues); Claude Code Desktop DCR expectations undocumented in places.
8. **Claude Code subscription constraint** — cloud cannot invoke Claude Code headless; the local bridge via MCP is pull-only from Claude Code side. Framework must not assume push-to-laptop.
