# Conexus Framework Design — 2026-04-16

> **Brand:** "You direct. Agents execute."
> Build one agent or a full team — each with a role, tools, budget, and memory.

## North Star

Conexus is a Python agent framework. It runs **one agent or many**. Single agent is the default; teams emerge naturally as you add more.

The operator is the director: define an agent by writing a `SKILL.md`, declare its tools, set its budget. The framework handles the loop, memory, scheduling, cost tracking, and security. The framework is honest by default: no runaway costs, no silent failures, no opaque black boxes.

**Valid use cases:**
- Single agent — Ana alone as a life OS; Pesquisador alone as a research bot
- Multi-agent team — Ana + Pesquisador + PM + internal specialists, coordinated via `delegate_to`
- Any combination — start with one, grow to many, same kernel

---

## Locked Decisions

### 1. Routing — Option C (Hybrid)
- **User-facing bots** (Telegram): Ana, PM, future Isaac
- **Internal specialists**: Coder, Reviewer, Analyzer, etc. — registered in AgentRegistry only, no Telegram token
- PM receives tasks from user-facing agents; delegates to specialists via `delegate_to` tool
- No fallback to other routing options

### 2. Plugin ecosystem — MCP (curated, no auto-install)
- Adopt MCP as the standard plugin surface (97M monthly downloads, Claude Desktop, VS Code native)
- Curated whitelist only — no auto-install from registries (ClawHub had ~20% malicious skills)
- Per-server permission scope defined in config
- Tool poisoning mitigation: validate tool metadata signatures before load

### 3. Wiki / retrieval — phased by corpus size
| Corpus | Approach |
|--------|----------|
| < 200 articles | Karpathy wiki pattern — full text in context |
| 200–2000 | BM25 (sqlite FTS5) |
| > 2000 | sqlite-vec hybrid |

Current Pesquisador: < 200 → full text. No premature vectorization.

### 4. Agent Directory — SKILL.md frontmatter extension
Each agent SKILL.md gains:
```yaml
capabilities:
  - research
  - web_search
  - wiki_write
when_to_use: "User asks for deep research, article compilation, or web search"
cost_tier: medium          # low | medium | high
visibility: internal       # internal | user_facing
wiki_root: knowledge       # relative subdir under data_dir/<agent_name>/
```
PM reads directory to know what each agent can do — no hardcoding.

### 4a. Per-Agent Wiki Namespace (framework standard)
Every agent owns an isolated wiki namespace. Convention enforced by framework:

- `wiki_root` declared in SKILL.md frontmatter (default: `wiki`)
- Framework creates `WikiStore(data_dir / <agent_name> / wiki_root)` automatically
- Each agent gets separate git-backed directory — no cross-agent wiki pollution
- Separate git repo per agent (env var: `<AGENT_NAME>_WIKI_REPO`)

Current state: Ana uses `data_dir/wiki/`, Pesquisador uses `data_dir/knowledge/` — hardcoded in `main.py`. Migration: move to SKILL.md-driven wiring in Phase 0.

Agent tools (`wiki_read`, `wiki_write`, `wiki_search`) always scoped to own namespace. Cross-agent wiki read requires explicit tool (`read_agent_wiki(agent="pesquisador", path="..."`) — not default.

### 5. Brand
- Tagline: **"You direct. Agents execute."**
- Sub: "Deploy specialist agent teams for any context."
- Director metaphor: operator sets SKILL.md (hiring), sets budget (constraints), sets tools (authority). Agent works within those rules.

---

## Phase 0 — Must ship before adding agents

These are security and stability gaps that affect production TODAY.

### P0-1: Trifecta Guard
**Problem:** Ana has all 3 conditions of Willison's "lethal trifecta" simultaneously:
- Private data (`private_read`): calendar, facts, Telegram history
- Untrusted content (`untrusted_read`): web_fetch results, Pesquisador output
- External comms (`external_write`): Telegram reply, wiki write, calendar create

**Design:** Tag tools in SKILL.md with data class:
```yaml
data_class: private_read | untrusted_read | external_write
```
`AgentHandlerConfig` reads tags. Turn-level policy enforced in `handle_agent_message`:
- A turn that called `untrusted_read` tool cannot call `external_write` carrying private content in same turn
- Violation → abort turn, Telegram warning to operator

### P0-2: Calendar / Email Content Sandbox
**Problem:** OWASP LLM01:2025. Indirect prompt injection via calendar events (Gemini CVE shipped Jan 2026). Ana reads Google Calendar event descriptions — those descriptions are attacker-controlled.

**Design:** `GoogleCalendarClient.get_events()` strips / flags instruction-like content from event descriptions before returning to LLM context. Pattern: detect imperative sentences, system-prompt-like formatting, "ignore previous instructions". Replace with `[CONTENT REDACTED - possible injection]` + log.

### P0-3: Loop Detection in BudgetCap
**Problem:** Current `CapChecker` counts tokens/cost. Doesn't detect repetition loops. Real incident pattern: agent calls same tool 40× in 2 min → $50/afternoon.

**Design:** Add per-turn tool-call counter to `agent_handler.py`:
```python
tool_call_counts: dict[str, int] = {}
# If same tool + same args called 3× in one turn → circuit break
```
Logs circuit break, notifies operator via Telegram, halts turn.

### P0-4: Memory Tiers (L0 / L1 / L2)
**Problem:** Every personal agent framework has the same bug: memory DB grows unbounded. No decay. No summarization. Users give up.

**Design:**
| Tier | Store | Retention | Content |
|------|-------|-----------|---------|
| L0 | `chat_history` table (SQLite) | 30 days | Raw turns, tool calls |
| L1 | `session_summaries` table | 180 days | Agent-generated summary post-session |
| L2 | `/data/wiki/` (git-backed markdown) | Forever | Verified long-term facts, research |

Demotion job (weekly cron): L0 older than 30d → agent summarizes → insert L1 → delete L0. L1 older than 180d → agent distills key facts → append to L2 wiki → delete L1.

### P0-5: Cache Discipline in ContextBuilder
**Problem:** Naive caching can increase latency on agentic workloads (arXiv 2601.06007). BRT timestamp bleeds into cached prefix → cache miss every turn.

**Design:** Enforce stable prefix ordering in `TrackedLLM` / `handle_agent_message`:
```
[System prompt — CACHED]
[SKILL.md body — CACHED]
[Agent directory (when relevant) — CACHED]
--- cache boundary ---
[L0 chat history (recent N turns)]
[Tool results this turn]
[Current BRT timestamp]  ← ALWAYS AFTER CACHE BOUNDARY
```
Move BRT timestamp to tail. Keep system prompt + SKILL body stable between turns.

### P0-6: Agent Directory + Curated MCP Whitelist
**Problem:** PM can't know what agents can do without hardcoding. MCP auto-install = security risk.

**Design:**
- Agent Directory: SKILL.md v2 with `capabilities`, `when_to_use`, `cost_tier`, `visibility` (see §4 above)
- `AgentRegistry` exposes `describe_agents()` → PM tool `list_available_agents()` returns structured directory
- MCP whitelist: `config/mcp_whitelist.yaml` — explicit server list with per-server tool scope. No dynamic loading from registries.

---

## Phase 1 — After Phase 0 stable

| Item | Description |
|------|-------------|
| Authorization middleware | Per-tool-call allow/deny/modify/defer/step-up (AgentLock pattern) |
| Resumable long tasks | Task ledger table; subgoal DAG checkpoint; survive Fly.io restart |
| Inter-agent message validation | Schema-check `delegate_to` results — treat as untrusted input |
| Autonomy slider | Per-tool `autonomy_level: ask\|confirm\|auto`; Telegram inline approve buttons |
| Hybrid routing (C) full | PM agent + internal specialists wired in `main.py` |
| Dynamic reminders | `reminders` table; poll job; replaces static SKILL.md cron |
| Cheap-router / premium-synthesis | Promote `llm:` + `llm_synthesis:` split to framework primitive in all SKILL.md |
| Langfuse self-hosted | Observability without 40-200% external bill markup |
| **Telegram Group Teams** | See below |

### Telegram Group Teams

Operator organizes agents into named teams. Each team gets its own Telegram group. Operator talks to manager; manager delegates to specialists internally.

**Topology:**
```
Telegram Group: "Product Team"
    → ProductManager bot (manager, user-facing)
        → Coder (internal, AgentRegistry only)
        → Reviewer (internal, AgentRegistry only)
        → Analyst (internal, AgentRegistry only)

Telegram Group: "Marketing Team"
    → MarketingManager bot (manager, user-facing)
        → ContentWriter (internal)
        → SEOAnalyzer (internal)

Direct chat: Ana (personal agent, no team)
```

**SKILL.md frontmatter extension:**
```yaml
team: product                    # team cluster name (omit = no team)
role: manager                    # manager | specialist (default: specialist)
telegram_group_id: -100123456   # Telegram group ID (manager only)
```

**Wiring in `main.py`:** one Telegram bot per manager agent. Same pattern as Ana + Pesquisador today. Framework iterates agents with `role: manager` → creates bot → registers group handler. No new patterns.

**Specialist agents:** never get direct Telegram access. Only reachable via `delegate_to` from their team manager. Operator cannot bypass manager to reach specialist directly.

**Trajectory logging:** each team namespace has isolated wiki. Trajectories stored under `/wiki/trajectories/<agent_name>/` — prerequisite for Phase 2+ AutoResearch.

---

## Phase 2+ — Deferred

### AutoResearch Loop (Karpathy pattern)

Agent NEVER auto-edits its own SKILL.md. Human gate always required. But the *experiment loop* is fully automated — operator triggers it, system runs N experiments, proposes winner.

**Prerequisites (Phase 1):** trajectory logging must exist. No trajectories = no frozen inputs = loop has nothing to measure.

**Trigger:** operator command: `"run full improvement on Pesquisador"`

**Loop mechanism:**
```
1. Orchestrating agent reads current SKILL.md → baseline
2. Reads /wiki/trajectories/<agent>/ → frozen inputs (real past task logs)
3. Generates hypothesis: "stricter citation rule", "shorter persona", etc.
4. Applies hypothesis to SKILL.md.candidate (temp file, not production)
5. Spins shadow instance:
     AgentHandlerConfig(candidate SKILL.md, same Tools class, fresh chat history)
6. Replays N frozen trajectory inputs through shadow instance
7. LLM-as-judge scores each candidate output vs baseline output
8. If candidate wins → keep hypothesis, try next
   If candidate loses → discard, next hypothesis
9. Best candidate → Telegram diff to operator
10. Operator approves → overwrite SKILL.md, git commit
11. Measure over next M real production turns
12. If production quality drops → git revert (one command, clean rollback)
```

**Shadow instance:** `AgentHandlerConfig` with candidate SKILL.md, isolated SQLite (no production data access), no Telegram output. Experiments never touch production.

**Scalar metric:** LLM-as-judge rating over N trajectory replays. For conversational agents, quality = relevance + accuracy + conciseness vs baseline.

**What this is NOT:** "PM does web research → writes better SKILL.md → human approves" = research-guided editing. Useful, but not AutoResearch. Label correctly in code and docs.

---

### Other Phase 2+ items

- Voice-in via Whisper V3 Turbo / Deepgram Nova on Telegram
- Wiki beyond markdown: BM25 when >200 articles, sqlite-vec when >2000
- Trajectory mining → `/wiki/trajectories/` (extract strategies from completed task logs) — **prerequisite for AutoResearch**
- MAST failure-mode test harness (replace pass/fail with 14-failure-mode coverage)
- FastAPI wiki web UI
- MCP expose: Conexus wiki as MCP server (Claude Desktop can consume)
- `/why` accountability command (which agent, which model, which context)
- Ollama / local model fallback for privacy-sensitive tools
- Multi-tenant isolation (per-deployment SQLite volume, isolated config)

---

## Framework Contract (unchanged from current ARCHITECTURE.md)

Core loop stays. Every addition MUST fit inside:

```
SKILL.md → SkillLoader → AgentHandlerConfig
Tools class → schema_gen → OpenAI tool schemas
handle_agent_message → tool-calling loop → AgentRegistry.execute_tool
```

No new loops. No new base classes. Additions are:
- Tags on SKILL.md (Phase 0)
- Policy enforcement in `handle_agent_message` (Phase 0)
- New tool methods in existing `Tools` classes (Phase 1)

---

## KPIs (from doc 14, unchanged)

| Metric | Target |
|--------|--------|
| New agent time-to-wire | < 30 min |
| Cost per reactive Ana turn | < $0.002 |
| Budget cap accuracy | No overrun > 10% |
| Test coverage core/ | > 80% |
| Trifecta guard coverage | 100% of untrusted_read tools tagged |
| L0→L1 demotion job | Running weekly without failure |

---

## What we're NOT doing

- No LangChain, LangGraph, CrewAI dependency — framework stays minimal
- No GroupChat / hierarchical CrewAI manager pattern
- No auto-install from MCP registries
- No vector DB before 200-article threshold
- No multi-tenant until Metal Shopping is ready to fork (deferred)
- No voice until P0+P1 stable

---

*Written 2026-04-16. Research sources: Willison lethal trifecta, MAST taxonomy arXiv 2503.13657, ossinsight agent memory race, OWASP LLM01:2025, arXiv 2601.06007 cache discipline, Karpathy LLM wiki gist, SitePoint personal agent OS paradigm, Geoffrey Litt "Stevens" pattern, AgentLock Apache 2.0.*
