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
