# 06 — Multi-Agent Orchestration

> Status: reference. Opinionated. Written for Conexus, which today runs **Ana** (secretary) and **Isaac/Pesquisador** (researcher) as two separate Telegram bots sharing one process, one SQLite, one scheduler, and zero formal inter-agent channels. This doc is the map for when (and when not) to add one.

---

## 1. Executive summary

Multi-agent is a distribution choice, not a capability. You do not get *new* reasoning by splitting one Claude into three Claudes — you get **parallelism**, **role isolation**, and **context compartmentalization**, while paying 5–15× more tokens and importing a fresh class of bugs (dropped handoffs, context drift, authority conflicts, infinite loops). Anthropic's own retrospective on their research system is blunt: multi-agent won when work was *parallelizable and breadth-first*; Cognition's counter-essay is equally blunt that it loses when work is *sequential, stateful, or stylistically coherent*.

For Conexus specifically: Ana and Isaac are **two single-agent systems that happen to cohabit**. That is fine. The next honest step is not "make them talk", it is to decide what job requires coordination that a single agent cannot do with a tool call. Until that job exists, any inter-agent protocol is premature infrastructure.

When a real coordination need arrives (Ana needs Isaac to produce a briefing before a meeting; Isaac needs Ana to schedule a follow-up), the cheapest move is a **function-call handoff through the existing `AgentRegistry`**, with a typed Pydantic payload and a trace id. Everything in sections 3–11 below is how that evolves if and only if it has to.

---

## 2. When multi-agent actually helps vs single-agent

### The case *for* multi-agent (Anthropic, June 2025)

Anthropic's "How we built our multi-agent research system" reports the production shape of Claude Research: an **orchestrator (Opus)** spawns 3–5 **subagents (Sonnet)** to explore different facets in parallel. Quoting directly:

> "agents typically use about 4× more tokens than chat interactions, and multi-agent systems use about 15× more tokens than chats"

> "These changes cut research time by up to 90% for complex queries"

The reported win over single-agent Opus on their internal eval was **+90.2%**. The decisive variables were (a) the problem decomposes into independent subtasks, (b) the combined information *exceeds a single context window*, and (c) tool calls dominate wall-clock time and benefit from fan-out. Coordination failures dominated early versions — orchestrators spawning 50 subagents for trivial queries, subagents redoing each other's work — and were only tamed with very explicit effort-scaling rules in the orchestrator prompt.

### The case *against* multi-agent (Cognition, June 2025)

Walden Yan's "Don't Build Multi-Agents" argues the opposite for software engineering and other stateful tasks. Two principles:

1. **Share context, and share full agent traces, not just individual messages.** Summaries leak.
2. **Actions carry implicit decisions; conflicting decisions produce bad results.** Parallel subagents silently make incompatible assumptions (the Flappy Bird example: one subagent builds Mario-style background art, another builds a bird that looks nothing like a game sprite — technically on-brief, actually incoherent).

The recommended shape is **single-threaded linear agents** with context-compression when you exceed the window, not fan-out.

### Steelman synthesis

Both are right about different problem classes:

| Use multi-agent when                                  | Stay single-agent when                           |
|-------------------------------------------------------|--------------------------------------------------|
| Work is embarrassingly parallel (search, scrape, map) | Work has sequential dependencies / shared style  |
| Subtasks have disjoint context needs                  | Every step depends on prior steps' fine detail   |
| Latency beats token cost                              | Token budget matters (Ana's `on_exceed: notify`) |
| Tool surface is huge and partitions by role           | Tool surface fits one system prompt              |
| Output is a collection (citations, candidates, leads) | Output is one coherent artifact (code, prose)    |

For Conexus: Ana's calendar/reminders work is sequential + stateful → single-agent. Isaac's `compile_article` is already a **pipeline of LLMs** (cheap router + Gemini synthesizer) inside one agent — that is a two-model single-agent, not multi-agent. A true second agent only pays off when Conexus grows a fan-out task (e.g. "research these 12 companies and produce a dossier").

---

## 3. Topologies

Five canonical shapes. Pick one per coordination problem; don't mix them in the same loop without a reason.

- **Supervisor / router.** One agent owns the plan and dispatches to workers. Workers return to the supervisor; supervisor decides next step. LangGraph's `create_supervisor`, OpenAI Agents SDK's triage-agent-with-`handoffs`, CrewAI's `Process.hierarchical`. Default choice.
- **Swarm / peer handoff.** No central router; each agent can hand off to any other. State travels with the handoff. LangGraph `langgraph-swarm`, OpenAI Agents SDK chained handoffs. Good when roles are symmetric; bad when you need global control.
- **Pipeline / sequential.** Fixed DAG: A → B → C. CrewAI's `Process.sequential` with `context=[prev_task]`. Good when stages are stable and debuggable; brittle when inputs vary.
- **Hierarchical (supervisor of supervisors).** Orchestrator spawns sub-orchestrators, each with their own workers. Anthropic's research system is this shape. Only justified when a single supervisor's tool list / prompt would explode.
- **Network / graph.** Arbitrary edges expressed as a state graph (LangGraph). Maximum flexibility, maximum debugging cost. Use when the coordination pattern is actually a graph and you can't collapse it.

For Conexus today, the honest shape is **two disjoint single-agent systems**. The first coordination work should be a **supervisor-on-demand**: Ana becomes the default entry point, Isaac is reachable through an `ask_isaac(question: str) -> str` tool. That is a supervisor topology implemented as a single tool call — the minimum viable multi-agent.

---

## 4. Handoff patterns

### OpenAI Agents SDK — handoffs as tools

The SDK exposes handoffs as auto-generated tools named `transfer_to_<agent>`:

```python
from agents import Agent, handoff, RunContextWrapper
from pydantic import BaseModel

class Brief(BaseModel):
    topic: str
    deadline: str

async def on_handoff(ctx: RunContextWrapper[None], data: Brief):
    # fire trace, persist handoff reason, enforce ACL
    ...

isaac = Agent(name="Isaac", instructions="You are a researcher.")
ana = Agent(
    name="Ana",
    instructions="You are a secretary. Hand off research tasks to Isaac.",
    handoffs=[handoff(agent=isaac, on_handoff=on_handoff, input_type=Brief)],
)
```

The `input_type` is the handoff contract — keep it small (reason, topic, deadline), never dump full history into the payload. Use `input_filter` if the receiving agent should not see the full upstream trace.

### LangGraph — `Command(goto=..., update=...)`

LangGraph handoffs are state-graph transitions. A node returns a `Command` telling the runtime which node runs next and what to merge into state:

```python
from langgraph.types import Command
from langgraph.graph import StateGraph, MessagesState

def ana_node(state: MessagesState) -> Command:
    if needs_research(state["messages"][-1]):
        return Command(goto="isaac", update={"messages": [...]})
    return Command(goto="__end__")
```

The key property: **state is shared by default** (single `MessagesState`). This is the opposite of the OpenAI SDK design and maps directly onto Cognition's "share the full trace" principle.

### CrewAI — tasks with `context`

CrewAI models delegation as a DAG of `Task`s bound to `Agent`s, with explicit context wiring:

```python
research = Task(description="Find top 5 sources on X", agent=isaac)
brief    = Task(description="Summarize for Leandro", agent=ana, context=[research])
Crew(agents=[isaac, ana], tasks=[research, brief], process=Process.sequential).kickoff()
```

Agents with `allow_delegation=True` can also delegate ad-hoc at runtime, but the `context=[...]` wiring is the predictable path.

### Verdict for Conexus

The current `AgentRegistry.execute_tool` already *is* a handoff mechanism; it just happens to be intra-agent. Model the first inter-agent call as a single tool on Ana that invokes Isaac's handler with a Pydantic `Brief` payload and returns a JSON string — identical shape to every other Conexus tool. Don't import a framework for one edge.

---

## 5. Shared state vs isolated

Three disciplines, in order of increasing complexity:

1. **Isolated + artifact passing.** Each agent owns its memory; coordination is via serialized artifacts (a markdown briefing, a JSON result). This is Conexus today: Isaac writes to `/data/wiki/`, Ana reads. Simple, auditable, git-backed.
2. **Shared scratchpad.** A common scratch area both agents can read/write during a single coordinated task. Implement as a SQLite table `coord_scratch(trace_id, agent, turn, content)`. Cheap, explicit, bounded.
3. **Blackboard.** A richer shared workspace with typed entries, subscriptions, and a coordinator that decides who acts on what. Classic AI pattern (Hayes-Roth, 1985); modern incarnations are LangGraph's shared state + conditional edges. Only worth it for >3 agents or when agents genuinely opportunistically contribute.

Rule: **the more you share, the less you can parallelize without conflicts**. Cognition's "share the full trace" and Anthropic's "parallelize aggressively" are in direct tension; you pick which side of that to buy per task.

For Conexus, wiki files are already a pseudo-blackboard — Isaac writes, Ana reads, humans edit. Formalize it before inventing a second one.

---

## 6. Inter-agent protocols

What is actually on the table in 2026:

- **Function-call as handoff.** The dominant de facto protocol. An agent calls `transfer_to_X(payload)` and the runtime routes it. Works inside one process. This is what OpenAI Agents SDK, LangGraph, and CrewAI all reduce to under the hood.
- **Typed messages over a queue.** A2A/ACP/in-house. An agent publishes a `Message` with `role`, `parts`, and a `task_id`; a subscriber picks it up. Necessary when agents run in separate processes or hosts.
- **A2A (Agent2Agent, Google).** JSON-RPC over HTTP, with SSE for streaming. Core nouns: `AgentCard` (metadata + skills + auth at a well-known URL), `Task` (lifecycle object), `Message` (role + `Part`s), `Artifact` (task output), `Part` (text / file / data). Use when Conexus needs to talk to a third-party agent you didn't write.
- **ACP (AGNTCY / Linux Foundation).** Adjacent goal, REST-first, less momentum as of early 2026. Track it; do not adopt yet.
- **MCP as tool-bridge.** MCP is not an inter-agent protocol — it is a *tool* protocol. But it is the right layer for "give Isaac access to Ana's calendar" without giving Isaac Ana's brain. Expose Ana's Google Calendar client as an MCP server; Isaac mounts it as tools. You get capability sharing without prompt coupling.

Opinion: for Conexus, **function-call handoff is the right default**, MCP is the right answer when you want to share a *tool* (calendar, wiki search) without sharing a persona, and A2A only matters the day Conexus must federate with an external agent.

---

## 7. Communication contracts

Whatever transport you pick, the *payload* must be typed. Pydantic in Conexus, always.

```python
# core/coord/messages.py
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime

class Handoff(BaseModel):
    schema_version: Literal["1"] = "1"
    trace_id: str
    from_agent: str
    to_agent: str
    intent: Literal["research", "schedule", "summarize"]
    payload: dict
    deadline: datetime | None = None
    reply_to: str | None = Field(None, description="chat_id or agent for the final response")
```

Rules:

- **Version every schema from day one** (`schema_version: "1"`). Migrations are cheaper than archaeology.
- **Never pass raw message history across agents.** Pass a compressed brief + a handle (trace id, wiki path) so the receiver can pull more if it needs to. This is the Cognition principle applied sanely.
- **Results are JSON strings** at the registry boundary (Conexus convention), Pydantic objects internally. Parse at the edge.
- **Reject unknown fields** in strict mode; log and accept in lenient mode. Pick one per direction.

---

## 8. Coordination hazards

Specific failure modes, each with the mitigation you should pre-commit to.

- **Infinite handoff loops.** A hands to B, B hands back to A, forever. Mitigate with a hop counter in `Handoff` (`max_hops=5`) and a hard stop in the runtime. Log the full path on abort.
- **Redundant work.** Two subagents fetch the same URL. Mitigate with a shared result cache keyed on `(tool_name, args_hash)` for the duration of a trace.
- **Context bloat.** Each handoff appends history; token cost grows quadratically. Mitigate with `input_filter` / compression briefs; never forward more than N messages without summarization.
- **Authority conflicts.** Ana and Isaac both decide to reply to the user. Mitigate by designating exactly one agent as `reply_to` per trace; others may only return artifacts.
- **Silent divergence.** Two parallel subagents make incompatible assumptions (Flappy Bird problem). Mitigate by (a) avoiding parallelism for stylistic work, (b) making the supervisor merge-and-reconcile before any output ships.
- **Budget blowout.** A 15× token multiplier is real. Mitigate by keeping `BudgetCap` per agent *and* per trace. Reject handoffs whose projected cost exceeds the trace budget.
- **Stale state.** Subagent reads a wiki file, another subagent overwrites it mid-run. Mitigate with optimistic locking (file hash) or single-writer discipline per trace.

---

## 9. Human-in-the-loop

Multi-agent systems hide decisions. HITL pulls them back.

- **Approvals on high-impact tools.** Before Ana sends an email or Isaac deletes a wiki page, require a Telegram confirm. Implement as a tool wrapper that posts an inline-keyboard message and blocks the agent on the reply. LangGraph calls this an `interrupt`; OpenAI Agents SDK calls it a `guardrail`.
- **Checkpointed resumes.** Persist the agent state at each handoff so a human can inspect, edit, and resume. LangGraph's checkpointer abstraction is the reference design; a `coord_checkpoint(trace_id, step, state_json)` SQLite table is the Conexus-scale version.
- **Guardrails as input validators.** OpenAI Agents SDK guardrails let you run a cheap classifier before the expensive agent runs — reject or escalate at the gate. Useful for Pesquisador where a single bad prompt can burn Gemini Pro tokens.
- **The human as an agent.** Model Leandro as a node in the graph with a `wait_for_reply(chat_id, timeout)` primitive. Then HITL is just another edge in the topology, not a special case.

For Conexus: start with approval wrappers on destructive tools (calendar delete, email send, `wiki_delete`), add checkpoints only once a trace routinely crosses agent boundaries.

---

## 10. Observability for multi-agent

You cannot debug what you cannot correlate. Minimum viable kit:

- **`trace_id` propagated everywhere.** Generate at the user's inbound message, attach to every tool call, every LLM call, every handoff, every log line. Conexus's `UsageTracker` already logs per-call cost — add `trace_id` as a column.
- **Per-agent spans.** OpenTelemetry or a homegrown `spans(trace_id, agent, parent_span, t_start, t_end, tokens_in, tokens_out, cost_usd)` table. Each agent invocation is a span; each tool call is a child span.
- **Cost attribution.** Roll up cost by `(trace_id, agent, model)`. Per-trace budget enforcement depends on this.
- **Event timeline.** A single chronological log per `trace_id`: "Ana received msg → Ana called `ask_isaac` → Isaac called `wiki_search` → Isaac returned brief → Ana sent reply". Anthropic's post explicitly credits this kind of timeline for taming their coordination bugs.
- **Replay.** Save inputs + seeds so you can rerun a trace with a modified prompt. Non-negotiable once handoffs exist.

LangSmith, Langfuse, and Arize Phoenix all do this out of the box; a Conexus-native schema is three tables (`traces`, `spans`, `events`) and takes a day to build.

---

## 11. Patterns

Proven multi-agent recipes. Each maps cleanly onto one of the topologies in §3.

- **Planner + executor.** Planner (smart model) produces a typed plan; executor (cheap model) runs each step. Classic supervisor shape. Good when plans are reusable and inspectable. *Conexus fit:* if Ana grows multi-step workflows ("plan my Tuesday"), split planner from executor on cost grounds alone.
- **Critic + actor.** Actor proposes; critic reviews; loop until critic approves or N rounds elapse. Swarm of two. Great for drafts (emails, posts). *Conexus fit:* Isaac's `compile_article` could adopt a critic pass before publication.
- **Researcher + writer.** Researcher gathers sources into a structured bundle; writer produces prose. Pipeline shape. *Conexus fit:* this is already Pesquisador's shape; the "writer" is the Gemini synthesis step — keep it single-agent until the researcher side needs to fan out.
- **Ensemble-of-experts.** N domain agents answer independently; a judge aggregates. Good for breadth queries, high-stakes classifications. Expensive. Only pay for it when disagreement carries signal.
- **Orchestrator + parallel subagents (Anthropic shape).** Orchestrator decomposes, 3–5 subagents work in parallel with disjoint contexts, orchestrator merges. The canonical breadth-first research pattern. *Conexus fit:* the day Isaac is asked "compare these 10 companies", this is the answer — not before.

---

## 12. Citations

- Anthropic, "How we built our multi-agent research system" (engineering blog), June 2025 — `https://www.anthropic.com/engineering/built-multi-agent-research-system`. Source of the 4×/15× token figures and the 90.2% eval delta.
- Cognition AI (Walden Yan), "Don't Build Multi-Agents", June 2025 — `https://cognition.ai/blog/dont-build-multi-agents`. Source of the two principles and the Flappy Bird failure example.
- OpenAI Agents SDK, "Handoffs" — `https://openai.github.io/openai-agents-python/handoffs/`. Handoff API, `on_handoff`, `input_type`, `input_filter`.
- LangGraph, "Multi-agent systems" — `https://langchain-ai.github.io/langgraph/agents/multi-agent/` and `/concepts/multi_agent/`. Supervisor, swarm, hierarchical, network patterns and `Command(goto=...)` semantics.
- LangGraph Swarm — `https://github.com/langchain-ai/langgraph-swarm-py`.
- CrewAI docs, "Tasks" and "Processes" — `https://docs.crewai.com/concepts/tasks`. Task DAG, `context`, `allow_delegation`, `Process.sequential` / `Process.hierarchical`.
- A2A Protocol specification — `https://a2a-protocol.org/latest/specification/`. AgentCard, Task, Message, Artifact, Part, JSON-RPC/SSE transports.
- Model Context Protocol — `https://modelcontextprotocol.io/`. Tool-sharing layer, not an inter-agent protocol, but relevant to §6.
- Hayes-Roth, "A Blackboard Architecture for Control", *Artificial Intelligence*, 1985 — foundational reference for §5.

---

**One-line takeaway:** Conexus should keep Ana and Isaac single-agent, add one function-call handoff with a typed Pydantic contract and a `trace_id` the day they must cooperate, and not import a multi-agent framework until the topology is too complex to draw on a napkin.

---

## 13. Conexus Phase 8 — TEAM_PACK runtime (shipped 2026-04-30)

> Status: implemented. Everything in this section is verified against `src/conexus/core/team/` at commit range d476101–6235bc8.

Phase 8 delivered the first real inter-agent substrate: a declarative team manifest format, runtime routing, budget enforcement, and audit. No existing single-agent behaviour changed — all new code is additive.

### 13.1 TEAM_PACK.md — the manifest format

A team is declared as a markdown file with YAML frontmatter. The reference pack lives at `agents/teams/product_team/TEAM_PACK.md`. The parser is `parse_team_pack()` (`src/conexus/core/team/team_pack.py:41`), which splits on `---` and passes the first YAML block to `TeamPackFrontmatter`.

**`TeamPackFrontmatter` fields** (`src/conexus/core/team/team_pack.py:22`):

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | `str` | yes | Team identifier |
| `version` | `str` | yes | Semver string |
| `manager` | `str \| None` | no | Agent name; must be in `members` if set |
| `members` | `list[str]` | yes | All agent names on the team |
| `edges` | `list[dict]` | no | Explicit routing edges (see §13.3) |
| `budget` | `TeamBudget` | yes | Pool + per-member shares |
| `policy` | `TeamPolicy` | no | Defaults: `trifecta_enforcement=strict`, `max_hops=5`, `max_turns=20` |
| `deployment` | `dict[str, str]` | no | Per-member deploy hints (`cloud`, `local`) |

**`TeamBudget`** (`src/conexus/core/team/team_pack.py:9`): `team_daily_usd: float`, `shares: dict[str, float]` (must sum to 1.0), `on_share_exceeded: Literal["notify", "halt_member", "borrow_from_pool"]`.

**`TeamPolicy`** (`src/conexus/core/team/team_pack.py:14`): `trifecta_enforcement`, `max_hops`, `max_turns`, `termination_text`.

### 13.2 TeamLoader — validation at load time

`TeamLoader(available_agents: set[str]).load(pack_path)` (`src/conexus/core/team/team_loader.py:7`) validates:

1. Every member in `members` exists in `available_agents` — fails fast with `ValueError("unknown member: <name>")`.
2. If `manager` is set, it must appear in `members`.
3. `budget.shares` must sum to 1.0 (tolerance ±0.01).
4. No share entry for an agent not in `members`.

Returns `TeamPackDocument` (frontmatter + body + pack_dir).

### 13.3 TeamRegistry — runtime view

`TeamRegistry(doc: TeamPackDocument)` (`src/conexus/core/team/team_registry.py:7`) is a thin runtime wrapper exposing:

- `.members` — `list[str]`
- `.manager` — `str | None`
- `.policy` — `TeamPolicy`
- `.budget` — `TeamBudget`
- `.has_member(name)` — bool
- `.edges_from(agent)` — list of edge dicts where `from == agent`

### 13.4 Handoff — the typed cross-agent envelope

`Handoff` (`src/conexus/core/team/handoff.py:8`) is a frozen Pydantic model. Fields:

| Field | Type | Default | Notes |
|---|---|---|---|
| `schema_version` | `Literal["1"]` | `"1"` | Schema guard |
| `from_agent` | `str` | required | Sending agent |
| `to_agent` | `str` | required | `"auto"` triggers router resolution |
| `payload` | `dict[str, Any]` | `{}` | Arbitrary task data |
| `context_mode` | `Literal["full", "last_message", "summary"]` | `"summary"` | History forwarding policy |
| `return_on` | `str \| None` | `None` | Agent name to return result to |
| `hop_count` | `int` | `0` | Incremented by `next_hop()` |
| `max_hops` | `int` | `5` | Hard limit; `next_hop()` raises at breach |
| `tags` | `set[DataClass]` | `set()` | Trifecta taint to seed in receiver |
| `trust_boundary_cleared` | `bool` | `False` | Bypasses Trifecta exfil rule in receiver |

`Handoff.next_hop(to_agent)` produces an immutable copy with `hop_count + 1`, new `from_agent` / `to_agent`, and raises `ValueError` if `max_hops` would be exceeded (see `src/conexus/core/team/handoff.py:24`).

### 13.5 HandoffRouter — four-step resolution

`HandoffRouter(registry: TeamRegistry).route(handoff: Handoff) -> str` (`src/conexus/core/team/handoff_router.py:20`) resolves the destination agent in this order:

1. **Explicit target.** If `to_agent != "auto"` and the agent is a valid member, return it directly.
2. **`auto: true` edge.** First edge from `edges_from(handoff.from_agent)` with `auto: true` — short-circuits remaining checks.
3. **`when` edge.** First edge where the `when` expression evaluates truthy against `handoff.payload` (Python `eval` with `{"__builtins__": {}}` and a `task` proxy binding `payload["task"]`).
4. **Manager fallback.** If `registry.manager` is set, return it.
5. **Raise.** `ValueError("no edge match and no manager")`.

The `when` expression sandboxing is intentionally minimal — edges are author-controlled, committed in the repo; the threat model is "developer shoots own foot", not untrusted input reaching eval (see `src/conexus/core/team/handoff_router.py:36`).

### 13.6 BudgetCascader — pool + share enforcement

`BudgetCascader(team_daily_usd, shares, policy)` (`src/conexus/core/team/budget_cascader.py:19`) tracks per-member spend against a shared pool. Three policies (matching `TeamBudget.on_share_exceeded`):

- **`notify`** — `check_and_debit()` returns `False` when share exceeded; caller decides how to signal the user. No halt.
- **`halt_member`** — member is added to `_halted`; subsequent calls raise `ShareExceeded`. Permanent within the `BudgetCascader` instance lifetime.
- **`borrow_from_pool`** — if the team pool has remaining headroom, the over-share cost is charged anyway; returns `False` only when the pool itself is exhausted.

`pool_remaining()` is the sum of all member spend subtracted from `team_daily_usd`.

### 13.7 Handoff audit — SQLite persistence

`src/conexus/core/memory/handoff_audit.py` ships a minimal audit table:

```sql
CREATE TABLE IF NOT EXISTS handoff_audit (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ts            TEXT NOT NULL,
  from_agent    TEXT NOT NULL,
  to_agent      TEXT NOT NULL,
  hop_count     INTEGER NOT NULL,
  tags          TEXT NOT NULL,
  trust_cleared INTEGER NOT NULL,
  payload_json  TEXT NOT NULL,
  outcome       TEXT NOT NULL
);
```

`init_handoff_audit(conn)` creates the table; `record_handoff(conn, handoff, outcome)` inserts one row per routed handoff. The `tags` column is a JSON array of `DataClass` values (sorted strings). `payload_json` is the full `handoff.model_dump_json()`.

### 13.8 Cross-agent TrifectaGuard integration

Phase 8 extended `TrifectaGuard` (`src/conexus/core/trifecta/guard.py`) with two new capabilities:

**`seed_taint` kwarg** (`guard.py:13`): pre-populates the turn's taint set before any tool call. Used when a receiving agent should inherit the sender's accumulated taint so the cross-agent boundary does not reset the Trifecta clock.

**`TrifectaGuard.from_handoff(tool_tags, handoff)` classmethod** (`guard.py:30`): constructs a guard for a receiving agent turn by reading `handoff.tags` as `seed_taint` and `handoff.trust_boundary_cleared` as the bypass flag. This is the canonical factory when an agent is invoked via a `Handoff`.

**Three-branch guard creation in `handle_agent_message`** (`src/conexus/core/agent_handler.py:61`):

```python
if cfg.tool_tags is None:
    guard = None                                          # guard disabled
elif cfg.incoming_handoff is not None:
    guard = TrifectaGuard.from_handoff(cfg.tool_tags, cfg.incoming_handoff)
elif ...:
    guard = TrifectaGuard(cfg.tool_tags)                 # normal single-agent turn
```

The `incoming_handoff` field on `AgentHandlerConfig` (`src/conexus/core/agent_handler.py:40`) carries the `Handoff` object; it is typed as `object | None` to avoid an import cycle at the dataclass definition site.

### 13.9 `conexus run-team` CLI subcommand

`conexus run-team <pack> [--available-agents <csv>]` (`src/conexus/cli/__main__.py:102`) validates a TEAM_PACK against a list of available agents and prints the loaded team name + member list. It is a dry-run validator, not a full team executor — the execution loop is future work.

### 13.10 Reference team pack

`agents/teams/product_team/TEAM_PACK.md` is the canonical example: a 3-member team (`ana`, `pm`, `researcher`), `pm` as manager, edges `ana→pm` (when `task.kind == 'plan'`), `pm→researcher` (when `task.kind == 'research'`), `researcher→pm` (auto), budget pool $1.00/day with shares 20/40/40.

### 13.11 Coordination hazard mitigations (Phase 8 update)

The hazard table in §8 is partially implemented now:

| Hazard | Phase 8 mitigation |
|---|---|
| Infinite handoff loops | `Handoff.max_hops` (default 5); `next_hop()` raises at breach (`src/conexus/core/team/handoff.py:27`) |
| Budget blowout | `BudgetCascader` with `halt_member` / `borrow_from_pool` policies (`src/conexus/core/team/budget_cascader.py`) |
| Cross-agent exfil (Trifecta) | `Handoff.tags` + `trust_boundary_cleared` + `TrifectaGuard.from_handoff()` propagate taint across the boundary |
| Missing audit trail | `handoff_audit` SQLite table; `record_handoff()` called per route decision |

Hazards without Phase 8 mitigation (still open): redundant work, context bloat, authority conflicts, silent divergence, stale state.

---

## 14. Conexus Phase 9 — Multi-Agent Runtime Activation + Replay + MCPProducer (shipped 2026-05-01)

> Status: implemented. All claims verified against `src/conexus/core/team/`, `src/conexus/core/memory/`, `src/conexus/core/mcp/`, `src/conexus/cli/__main__.py`.

Phase 9 activates the team runtime loop (`handle_team_message`), adds deterministic session replay, ships an MCPProducer server, and hardens several Phase 8 types. No existing single-agent behaviour changed.

### 14.1 `handle_team_message` — the multi-agent execution loop

`handle_team_message(*, team, configs, store, cap_checker, body, session_id, progress)` (`src/conexus/core/agent_handler.py:186`) is the new team entry point. It replaces the validate-only `run-team` stub with a real stack-based loop.

**Key behaviours:**

- **Entry point.** Starts at `team.manager` (or `team.members[0]` if no manager). Requires an `AgentHandlerConfig` for each member in `configs`.
- **Tool injection.** On each turn, the active agent's `tools_schema` is merged with `build_delegate_schemas(team, agent_name)` — the LLM sees both its own tools and `delegate_to_<sibling>` tools side-by-side.
- **Delegation dispatch.** When the LLM emits a `delegate_to_<X>` call, `parse_delegate_call` extracts `(target, payload, opts)`, a new `Handoff` is built (or `next_hop()` called on an existing one), the router resolves the target, `trim_transcript` applies `context_mode`, and a new `_Frame` is pushed onto the stack.
- **Return semantics.** A child frame pops itself when: (a) it emits a plain-text reply and there is no `return_on`, (b) `return_on` text is found in the reply. On pop, the parent frame receives `[returned from <child>]: <reply>` as a user message. `termination_text` (default `"DONE"`) in any reply terminates the entire loop immediately.
- **Serial-only.** `max_parallel_members=1` is enforced by breaking after the first `delegate_to_` call per turn — a second delegation in the same tool-call batch is not processed until the parent's next turn.
- **Tool audit.** Every non-delegate tool call records via `record_tool_call(audit_conn, session_id=..., ...)` (`src/conexus/core/memory/tool_audit.py`). Trifecta-blocked calls record `outcome="trifecta_blocked"`.
- **Cross-agent Trifecta.** The parent guard's current taint is captured via `guard.tainted_with()` and seeded into the child guard via `TrifectaGuard.from_handoff()`. The child cannot reset the Trifecta clock by hopping agent boundaries.
- **Session ID.** If `session_id` is `None`, a random `sess-<12 hex>` is generated. Propagated to both `record_handoff` and `record_tool_call`.

### 14.2 `delegate_tool.py` — LLM-facing delegation schema

`src/conexus/core/team/delegate_tool.py` contains two public symbols:

- `DELEGATE_PREFIX = "delegate_to_"` — the canonical prefix; the team loop uses `fn_name.startswith(DELEGATE_PREFIX)` to detect delegation.
- `build_delegate_schemas(registry, current_agent) -> list[dict]` — generates one OpenAI function schema per sibling member. Each schema has three parameters: `task` (required, free-form object), `context_mode` (enum of `full|last_message|summary`), `return_on` (optional string).
- `parse_delegate_call(tool_name, args) -> (target, payload, opts)` — validates and extracts the three fields. Raises `ValueError` for missing `task`, invalid `context_mode`, or empty target name.

### 14.3 `transcript.py` — context_mode trimming

`trim_transcript(messages, mode)` (`src/conexus/core/team/transcript.py:5`) trims the parent agent's message list before passing to the child:

| `context_mode` | What the child sees |
|---|---|
| `full` | Full copy of parent's messages |
| `last_message` | Only the last non-system message |
| `summary` | Single synthetic system message: `"Transcript summary: N prior message(s) elided by handoff context_mode=summary."` |

Default is `summary` (matches `Handoff.context_mode` default). The `handle_team_message` loop inserts the child agent's system prompt if none is present in the trimmed transcript.

### 14.4 Session replay — `replay.py`

`replay_session(conn, *, session_id, registry) -> ReplayReport` (`src/conexus/core/team/replay.py:29`) replays a frozen audit session against a (possibly changed) registry to detect routing regressions.

**Algorithm:**

1. Queries `handoff_audit` for all rows with `session_id=?`, ordered by `id`.
2. For each row, reconstructs a `Handoff` from `(from_agent, recorded_to, payload_json)` and calls `router._resolve(h)`.
3. If `resolved != recorded_to`, records a `ReplayMismatch(kind="route", expected=recorded_to, actual=resolved)`.
4. Counts `tool_audit` rows for the session and reports as `tools_replayed`.

**Return type:** `ReplayReport(handoffs_replayed: int, tools_replayed: int, mismatches: list[ReplayMismatch])`.

`ReplayMismatch(kind, expected, actual, detail)` — `kind` is `"route"` or `"missing_member"`.

### 14.5 Tool audit — `tool_audit.py`

`src/conexus/core/memory/tool_audit.py` adds a `tool_audit` table:

```sql
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
```

`init_tool_audit(conn)` — idempotent DDL. `record_tool_call(conn, *, session_id, agent, tool, args, result, outcome)` — inserts one row; `args` is serialised via `json.dumps(args, sort_keys=True)`.

`SqliteStore.init_db()` now calls `init_tool_audit` alongside `init_handoff_audit` (`src/conexus/core/memory/sqlite_store.py:87`). `SqliteStore.conn` is a new property that opens an unclosed connection (caller responsible for `.close()`), used by `handle_team_message` to hold a single audit connection across the full session (`src/conexus/core/memory/sqlite_store.py:91`).

### 14.6 Phase 9 changes to existing Phase 8 types

**`Handoff.trust_boundary_cleared`** changed from `bool` to `str | None` (`src/conexus/core/team/handoff.py:22`). A non-`None` string value means the boundary was cleared (legacy `True` → `"legacy:phase-8"` via `field_validator`; legacy `False` → `None`). This makes the reason auditable.

**`Handoff.tags`** (`set[DataClass]`) now propagates through the full hop chain via `next_hop()` — `model_copy(update={...})` preserves `tags` from the parent unless explicitly overridden.

**`TrifectaGuard.tainted_with() -> set[DataClass]`** added (`src/conexus/core/trifecta/guard.py:45`) — returns a snapshot of the current taint set. Used by the team loop to seed the child guard before delegation.

**`TrifectaGuard.clear_boundary(reason: str)`** now requires a non-empty, non-whitespace reason; raises `ValueError` otherwise (`src/conexus/core/trifecta/guard.py:29`).

**`TeamPolicy.max_parallel_members: int = 1`** added (`src/conexus/core/team/team_pack.py:19`), validated `>= 1` via `field_validator`. Phase 9 is serial-only; this field is a forward gate for future parallel dispatch.

**`handoff_audit` table** gained a `session_id TEXT NOT NULL DEFAULT 'legacy'` column (`src/conexus/core/memory/handoff_audit.py:12`). `init_handoff_audit` runs an idempotent `ALTER TABLE` for pre-existing tables. `record_handoff` accepts a `session_id=` kwarg (default `"legacy"`) (`src/conexus/core/memory/handoff_audit.py:32`).

**`McpStdioBackend._call`** uses `asyncio.Lock` (`self._call_lock`) for JSON-RPC id correlation; frames without `"id"` (notifications) are skipped; frames with a stale `id` are dropped defensively (`src/conexus/core/backends/mcp_stdio_backend.py:47–67`). The backend also populates `self._tool_names` via `tools/list` during `start()`.

### 14.7 MCPProducer — Conexus as MCP server

`build_mcp_producer(*, wiki_root, bearer_token) -> FastMCP` (`src/conexus/core/mcp/producer.py:36`) is the Phase 9 implementation of the §9b skeleton. It uses `fastmcp` and exposes:

- **`verify_bearer(token: str) -> {"ok": true}`** — bearer validation tool; stdio transport has no HTTP headers, so the client calls this after `initialize`. Internally calls `check_bearer(f"Bearer {token}", expected=bearer_token)` with `hmac.compare_digest` constant-time comparison.
- **`wiki_search(query: str) -> list[{"path", "size"}]`** — literal substring scan across `*.md` files under `wiki_root`, up to 20 hits.
- **`wiki://{path}` resource (`wiki_page`)** — returns raw markdown of a file at `wiki_root/path`. Path is sandboxed: `target.resolve()` must start with `wiki_root.resolve()`.

Phase 9 scope: stdio transport only. Streamable HTTP and scope-based access control are explicitly deferred.

`check_bearer(authorization_header, *, expected)` (`src/conexus/core/mcp/producer.py:22`) is a standalone helper for HTTP transports (future use). Raises `BearerError` on missing header, wrong scheme, or wrong token.

### 14.8 CLI additions

Two new `conexus` subcommands added in `src/conexus/cli/__main__.py`:

**`conexus mcp-server [--wiki-root PATH]`** — runs `build_mcp_producer` with `CONEXUS_MCP_TOKEN` env var as the bearer token, then `server.run(transport="stdio")`. Fails with `SystemExit` if the env var is unset.

**`conexus replay <pack> --db <path> --session-id <id> [--available-agents <csv>]`** — loads a TEAM_PACK via `TeamLoader`, opens the SQLite DB, runs `replay_session`, and prints `handoffs_replayed`, `tools_replayed`, and any mismatches.

### 14.9 Coordination hazard update (Phase 9)

| Hazard | Phase 9 mitigation |
|---|---|
| Authority conflicts | `termination_text` (default `"DONE"`) terminates the loop; `return_on` returns control to a specific agent — no implicit broadcasting |
| Stale routing | `conexus replay` compares recorded routes against current registry; mismatches surfaced before deploy |
| Cross-agent exfil (Trifecta) | `TrifectaGuard.tainted_with()` seeds child guard; `trust_boundary_cleared` is now a reason string, not a silent bool |
| Missing tool audit | `tool_audit` table + `record_tool_call` covers every non-delegate call in team sessions |

Hazards still open: redundant work, context bloat (partial: `trim_transcript` limits forwarding), silent divergence.
