# 15 — Future Vision

> Audience: Leandro + Claude. **Not v2 scope.** This file captures direction so we don't accidentally re-decide it every six months. Add to it. Do not implement from it without a spec.

---

## 1. Why this file exists

Conexus v2 (`docs/superpowers/specs/2026-04-29-conexus-framework-v2.md`) ships
a kernel, SKILL_PACK / TEAM_PACK, MCP producer + consumer, deterministic
guardrails. After v2 ships, the framework is *complete enough* to run real
teams. The pieces below are what come **after** that — the moves that turn
Conexus from "a working personal-agent framework" into "an ecosystem others use
without us holding their hand."

Each section: **what**, **why it matters**, **gating signal** (what triggers
us to actually build it).

---

## 2. Marketplace — agents, skills, teams as packages

### 2.1 What

A registry like Smithery / Pulse-MCP but for Conexus packs:

- **SKILL_PACK** — single tool bundle (`kanban`, `web-search`, `notion-sync`)
- **TEAM_PACK** — pre-wired team (`product-team`, `research-squad`, `ops-on-call`)
- **AGENT_PACK** — single agent + its skills + persona, ready to drop in

Pack metadata:

```yaml
name: research-squad
version: 1.2.0
type: team
authors: ["leandro@example.com"]
license: MIT
homepage: https://github.com/leandro/conexus-research-squad
runtime_requires: conexus >= 0.5
skills_required: [web-search@^0.3, wiki@^1.0]
budget_default_usd: 0.50
trifecta_profile: strict
signature: <ed25519 sig over manifest>
```

Discovery surfaces:

- `conexus search team:research`
- `conexus install team/research-squad@latest`
- web UI catalogue (read-only first)

### 2.2 Why it matters

Three flywheels pack distribution unlocks:

1. **Compounding work.** Skill written once, every Conexus user inherits it. Today Ana's `calendar_*` lives in our repo only; in marketplace shape it's `pip install conexus-skill-calendar`.
2. **Reference packs as documentation.** New users learn the framework by inspecting working packs, not by reading SKILL_PACK.md docs.
3. **Network effects.** A pack that depends on another pack creates incentive to keep upstream packs maintained.

### 2.3 Gating signal

**Build registry only after 3+ packs exist internally** (chicken-egg avoidance).
The 2026-04-24 draft flagged this risk explicitly. Reference packs we'd ship
first to bootstrap:

1. `conexus-skill-wiki` (extract today's WikiStore + tools)
2. `conexus-skill-calendar` (extract Ana's calendar tools)
3. `conexus-team-research` (Ana + Pesq + future Researcher pre-wired)

Until those three exist, marketplace is premature infrastructure.

### 2.4 Hard problems we'll meet

- **Signing + trust.** Composio / ClawHub research showed ~20% malicious-skill rate in unsigned MCP registries. Conexus marketplace must sign packs (ed25519 keypair per author) and verify on install. Curated allow-list as v1; community submissions only after signing infra is solid.
- **Versioning + compat.** Skills depend on framework version. SemVer + `runtime_requires` in manifest. CI gate that test-loads packs against framework HEAD.
- **Trifecta profile per pack.** A skill ships with a recommended `data_class` map; framework respects it but operator can override. Marketplace UI must surface trifecta posture so operators see "this skill includes `external_write` tools" before install.
- **Sandbox.** Pack tools run in operator's process. Code-execution risk is real. Two strategies: (a) MCP-stdio backend forces process isolation; (b) optional WASM / nsjail for in-proc tools. Pick after first malicious-pack incident.

### 2.5 Adjacent ecosystems to learn from

- **Smithery, Pulse MCP** — MCP server registries, same shape minus team primitives.
- **Hugging Face Hub** — model registry; auth + signing model is closest analog.
- **PyPI** — every problem we'd hit, they hit. Look at typo-squatting + namespace-hijack mitigations before designing ours.

---

## 3. Visual team-builder UI

### 3.1 What

Web UI for non-developers to compose teams without writing YAML:

- Drag agents onto canvas
- Wire edges (drag from agent A output → agent B input)
- Click skill → pick from marketplace
- Set budgets via sliders
- Toggle Trifecta profile
- Export → `TEAM_PACK.md` (or deploy directly)

Framework stays YAML-first; UI is **a generator**, not a parallel runtime.

### 3.2 Why it matters

- **Onboarding.** Most operators won't write `TEAM_PACK.md` from scratch.
- **Visualisation.** Edges + handoff topology are easier to reason about as graphs than as YAML.
- **Live observability.** Same canvas can render trace data — show which member fired, which edge transitioned, where budget went. "Editor and inspector are the same view" pattern.

### 3.3 Gating signal

**Build only after 5+ external operators have shipped teams.** UI without users
is a maintenance tax. If marketplace + CLI flow is friction-free for the first
five users, UI may not be needed at all.

Stack candidates (when the time comes): React Flow + shadcn/ui + Conexus REST
adapter. The REST adapter must exist first (a sister concern to MCP).

---

## 4. A2A — federation across systems

### 4.1 What

[Agent-to-Agent](https://github.com/google/A2A) protocol (Google, 2025) lets
agents in different organisations / clouds collaborate. Core nouns:

- **AgentCard** — `.well-known/agent.json`, advertises skills + auth
- **Task** — lifecycle object, statuses, artifacts
- **Message** — typed parts (text, file, data)
- **Artifact** — task output

A2A is **MCP's complement**: MCP = agent ↔ tool. A2A = agent ↔ agent.

### 4.2 Why it matters

- **Cross-org teams.** Metal Shopping operator wants to delegate to a vendor's pricing-research agent — A2A is the on-ramp.
- **Public agent endpoints.** Conexus team exposes itself at `https://conexus.example.com/.well-known/agent.json`; any A2A-compliant client (Google's, OpenAI's, anyone's) can route work to it.
- **Decoupling from MCP for cross-host comms.** Today Conexus exposes itself via MCP, which works but reuses a tool protocol for what is really agent-comms. A2A is the right layer.

### 4.3 Gating signal

**Wait until A2A converges with MCP** (per `docs/wiki/agents-framework/11-mcp.md`
§10 — 2026 roadmap names this convergence). Building A2A native today =
building on protocol that may be merged or superseded. Track via:

- `blog.modelcontextprotocol.io` 2026 roadmap posts
- A2A repo activity + spec stability

When two of the three major host vendors (Anthropic, OpenAI, Google) ship
production A2A clients, build.

---

## 5. Signed pack supply chain

### 5.1 What

Per-author keypairs, manifest signatures, framework verification on install:

```
$ conexus install team/research-squad@1.2.0
verifying ed25519 signature for leandro@example.com... ok
trifecta profile: strict (5 tools, 2 external_write, 0 unscoped)
budget default: $0.50/day
proceed? [y/n]
```

### 5.2 Why it matters

Every other agent ecosystem has been hit by malicious packs already (npm, PyPI,
Composio MCP, Cursor server squatting). Building signing infra **before** the
first incident is cheaper than after. Catalyst will be one supply-chain attack
on a Conexus consumer; pre-empting that is worth ~1 week of work.

### 5.3 Gating signal

**Build with marketplace v1.** Don't ship the registry without signatures.
Treat as one shipped item, not two phases.

---

## 6. Voice + multimodal

### 6.1 What

- Voice-in (Whisper / Gemini Audio) — already partial via Telegram voice notes
- Voice-out (TTS) — agents reply by audio when user opted in
- Image-in (vision models) — handle screenshots, diagrams, photos
- Image-out (image gen) — agent emits charts / diagrams / illustrations

### 6.2 Why it matters

- Voice is the highest-leverage I/O for personal agents (driving, walking, kitchen).
- Vision unlocks classes of help that text-only can't: "what's wrong with this PR diff?", "summarize this whiteboard photo", "diagnose this error screenshot".

### 6.3 Gating signal

- **Voice-in:** already partial (Telegram). Promote when latency + cost are stable.
- **Voice-out:** wait for native TTS in Anthropic / Gemini APIs (likely 2026-Q3).
- **Vision:** ad-hoc per agent today; promote to first-class skill primitive once 2+ agents need it.

Framework primitive: `Skill.modality` field (`text | voice | image | video`)
in SKILL_PACK manifest, multiplexed at the LLM-call layer.

---

## 7. Multi-tenant deployment

### 7.1 What

One Conexus instance hosting multiple operators' teams + data, isolated by
auth + namespace + per-tenant SQLite (or shared DB with row-level security).

### 7.2 Why it matters

Metal Shopping is the first concrete consumer who'd want this. Each Metal
Shopping client = a tenant; their PM agent + skills + wiki = their namespace.

### 7.3 Gating signal

**Build only when first paid Metal Shopping deal closes.** Premature
multi-tenant = wasted abstractions. Until then, single-tenant per Fly app
deployment is correct.

Hard parts when we get there:

- Per-tenant LLM keys + budget sandboxing
- Wiki repo per tenant (today's Ana / Pesq pattern generalised)
- OAuth scope = tenant boundary (delays #1.7 spec OAuth deferral becoming a problem)
- Compliance posture (GDPR, SOC 2) — out-of-scope for hobby project, in-scope for SaaS

---

## 8. AutoResearch / self-improvement loops

### 8.1 What

Agents that update their own SKILL.md based on observed performance:

- Pesquisador notices users keep asking for citations in a specific format → updates own prompt fragment.
- Ana notices she keeps misclassifying a particular intent → adds an example to her SKILL.md.
- Framework-level: skill embedding index notices unused tools → suggests pruning.

### 8.2 Why it matters

Manual prompt-engineering is the single biggest sink of operator time. If the
agent + framework can detect drift and propose edits (gated by human review),
operator becomes a reviewer, not an author.

### 8.3 Gating signal

**Build after Phase 1 evals + nightly consolidator have 3 months of data.**
You can't improve what you can't measure. Per target arch §11 OQ#8: "sleep-time
core-block editor: separate agent or nightly job?" — answer waits for data.

---

## 9. Sandboxing tiers

### 9.1 What

Three levels of execution isolation, picked per skill:

| Tier        | Mechanism                | Use for                             |
|-------------|--------------------------|-------------------------------------|
| `inproc`    | direct Python call       | trusted, hot-path tools             |
| `subprocess`| MCP-stdio                | third-party packs, untrusted code   |
| `sandbox`   | nsjail / firecracker / WASM | code-exec tools, marketplace tools  |

### 9.2 Why it matters

Marketplace packs run on operator hardware. One malicious `wiki_search` that
also reads `~/.ssh/id_ed25519` = lights out. MCP-stdio gives process isolation;
real sandboxing gives system-call isolation.

### 9.3 Gating signal

**Build with marketplace v1**, but `inproc` + `subprocess` are sufficient until
we accept community-submitted packs. WASM / nsjail tier is a same-day-as-public-marketplace concern.

---

## 10. Cost-aware planning

### 10.1 What

Framework-level planner that, before delegating, projects token cost across the
delegation tree and aborts if it exceeds budget. Today: BudgetCascader catches
overages reactively. Future: pre-execution estimate.

```
ana: "delegate to pm with this brief"
[planner] estimated cost: pm $0.12, architect $0.30, scribe $0.05 = $0.47
[budget] team_daily remaining: $0.40
[planner] aborting — over budget by $0.07
```

### 10.2 Why it matters

The Anthropic multi-agent retrospective ([wiki §06.2.1]) flagged that
orchestrators spawning unbounded subagents was their hardest tame problem.
Pre-execution cost projection is one of the strongest mitigations.

### 10.3 Gating signal

**Build after 1 incident of accidental fan-out blowing daily budget.** Premature.
Reactive BudgetCascader is enough until we have a real cost-blowout post-mortem.

---

## 11. Adjacent vision items (parking lot)

Less developed; capture so they don't get lost:

- **Replay debugger.** Pick a `trace_id` from production, re-run against current SKILL_PACK / TEAM_PACK, diff the outputs. Catches regressions across pack upgrades.
- **Eval-as-PR.** Operator changes SKILL.md → CI runs golden set against new prompt → posts cost / quality delta as PR comment.
- **Agent-level ACLs.** "Researcher cannot read Ana's wiki" expressed declaratively in TEAM_PACK; framework enforces at SkillRegistry dispatch.
- **Cross-agent memory (shared core blocks).** Letta-style shared facts across team members. Today each agent has own wiki — formalise selective shared blocks.
- **Drift detection on real users.** Telemetry on prompt-cache-miss spikes, tool-error spikes, latency regressions.
- **Conexus-as-MCP-host marketplace.** Same registry surface, different direction: a place that lists *third-party* MCP servers Conexus can consume safely (curated allow-list).

---

## 12. What stays out of vision (probably forever)

Things we have actively decided are not Conexus' job:

- **Replacing LangGraph / Letta as a general-purpose agent runtime.** We are personal-team-shaped, not graph-execution-engine-shaped.
- **Becoming a PaaS.** Hosting + scaling are deploy concerns; framework stays deployable on any Python host.
- **Generic chatbot platform.** Conexus is opinionated about teams + skills + memory + budget. A "build any chatbot" framework is a different product.
- **Owning the LLM provider relationship.** LiteLLM is the abstraction; Conexus does not run its own gateway / cache / fallback service.

These limits are features. Saying no to them keeps the kernel under 2 kLOC.

---

## 13. How this file evolves

- Add sections when a new direction surfaces and you want to remember it.
- Update gating signals when one fires (delete the section + reference the spec that supersedes it).
- Periodically (~6 months) re-read top to bottom, prune sections that no longer matter.
- Linked from `docs/superpowers/specs/2026-04-29-conexus-framework-v2.md` §11 ("Out of scope").

---

*Last revised 2026-04-29. This file describes intent, not commitment.*
