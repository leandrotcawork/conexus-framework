# LLM Agent Frameworks — 2025/2026 Survey

**Audience:** senior engineer building Conexus (Python, LiteLLM, SQLite, APScheduler, Telegram, markdown wiki memory). Written for decision-making, not marketing. Each entry: core abstraction, strengths, weaknesses, pick-it-when, snippet if load-bearing, link.

The landscape in April 2026 has consolidated around a handful of patterns: **stateful graphs** (LangGraph), **handoffs + runner loop** (OpenAI Agents SDK, Anthropic Claude Agent SDK), **role-based crews** (CrewAI, Agno), **self-editing memory** (Letta), and **declarative optimization** (DSPy). Most frameworks have shipped 1.0. LangChain's AgentExecutor and LCEL pipes were formally deprecated in LangChain 1.0 (Sep 2025). Microsoft put AutoGen into maintenance mode in favor of the Microsoft Agent Framework (MAF).

---

## 1. LangChain (+ LCEL)

**Core abstraction:** `Runnable` protocol — any component (prompt, model, retriever, tool) implements `invoke/stream/batch/ainvoke`. LCEL composed them with the `|` operator.

**Status in 2026:** LangChain 1.0 (Sep 2025) marks a reset. `AgentExecutor` and the old `initialize_agent()` are deprecated. LCEL pipes are discouraged — the new idiomatic path is the `create_agent()` wrapper that sits on top of LangGraph. LangChain itself is increasingly a thin "batteries" layer (loaders, integrations, output parsers); the execution engine is LangGraph.

**Strengths:** Unmatched integration surface (hundreds of loaders, vectorstores, tools). Output parsers are genuinely useful. Standard Runnable interface is still the cleanest ergonomics for pipelines.

**Weaknesses:** Long history of churn. Abstractions on abstractions. LCEL's `|`-overloading is clever but obscures stack traces. Agents inside LangChain proper are now a thin wrapper — you're paying import weight for something LangGraph already does.

**Pick when:** You need a retrieval/chain pipeline and want pre-built loaders; you are not building a multi-step agent loop from scratch.

**Skip when:** You want a lean agent runtime. Use LangGraph directly, or PydanticAI.

Docs: https://python.langchain.com — Repo: https://github.com/langchain-ai/langchain

---

## 2. LangGraph

**Core abstraction:** A state machine. You define a `StateGraph` with typed state (usually a `TypedDict`), register nodes as functions `(state) -> state_patch`, and add edges (conditional or unconditional). A `checkpointer` (SQLite, Postgres, Redis) snapshots state per step, keyed by `thread_id`. `interrupt()` pauses execution mid-node for human-in-the-loop.

**Strengths:**
- **Durable execution.** Crash mid-step, resume from last checkpoint. Same primitive powers time-travel debugging and HITL.
- **Cycles are first-class.** Unlike a DAG framework, loops are natural — tool-call-then-respond loops, planner-critic loops, multi-agent debate.
- **Streaming.** Token, step, and state-delta streams are built in.
- **Production-ready.** LangGraph Platform offers managed deploy; self-hosted Postgres checkpointer is solid.

**Weaknesses:** Verbose — a three-node graph is 40+ lines of boilerplate. State-patch semantics (reducers, `Annotated[list, add_messages]`) take a few reads to click. Debugging requires LangSmith or heavy logging.

**Pick when:** You need interrupts / HITL, long-running workflows with durability guarantees, or parallel fan-out/fan-in. This is the frontier for production agent orchestration.

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

graph = StateGraph(AgentState)
graph.add_node("plan", plan_node)
graph.add_node("act", act_node)
graph.add_conditional_edges("act", route, {"continue": "plan", "done": END})
app = graph.compile(checkpointer=SqliteSaver.from_conn_string("state.db"))
app.invoke(input, config={"configurable": {"thread_id": "user-42"}})
```

Docs: https://docs.langchain.com/oss/python/langgraph — Repo: https://github.com/langchain-ai/langgraph

---

## 3. OpenAI Agents SDK (ex-Swarm)

**Core abstraction:** `Agent` + `Runner`. An agent has instructions, tools, an output type, and a list of `handoffs` (other agents). The Runner loop calls the model, dispatches tools, and follows handoffs (which are surfaced to the LLM as `transfer_to_<agent>` tools). Guardrails are input/output validators that raise a tripwire exception. Tracing is on by default and ships spans to the OpenAI dashboard (or any OTel backend).

**Strengths:** Smallest readable codebase of any production SDK (~few thousand LOC). Handoffs are the cleanest multi-agent pattern shipping. Guardrails running in parallel with the main call is the right default. Tracing "just works." Works with any LiteLLM-compatible model.

**Weaknesses:** Loop is opinionated — you cannot easily insert custom control flow mid-turn like you can in LangGraph. No built-in durable state; if the process dies mid-run, you restart. Guardrails are per-invocation, not per-tool-step.

**Pick when:** Multi-agent system where specialized agents hand off cleanly (support triage → refund agent → escalation). Single-process, non-durable.

```python
from agents import Agent, Runner, handoff
triage = Agent(name="Triage", handoffs=[refund_agent, billing_agent])
result = Runner.run_sync(triage, "My card was charged twice")
```

Docs: https://openai.github.io/openai-agents-python/ — Repo: https://github.com/openai/openai-agents-python

---

## 4. Anthropic Claude Agent SDK + Skills

**Core abstraction:** A Python/TS harness wrapping the Messages API with first-class **tool use**, **file system access**, **sub-agents**, and **Skills**. Skills are folders (`SKILL.md` + scripts + resources) that Claude loads *progressively* — the frontmatter description is always in context, the body is loaded on demand, and referenced scripts are executed in sandbox. Shared across Claude.ai, Claude Code, and the SDK.

**Strengths:** Skills are the most interesting idea in 2025/2026 — they push framework logic out of Python and into markdown + shell, which is where it belongs for "how do I write a weekly report." Progressive disclosure fixes the "stuffed system prompt" antipattern. The SDK's context-editing primitive (the model can compact its own history) is unique.

**Weaknesses:** Claude-specific. Skills require a code-execution container. Python SDK is newer than the TS one and still churning. No built-in multi-agent orchestration beyond sub-agent spawning.

**Pick when:** You are committed to Claude and want Skills. Also: if you want to copy the Skills pattern into your own framework (which Conexus's `SKILL.md` already does).

Docs: https://code.claude.com/docs/en/agent-sdk/overview — Skills: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills — Skills repo: https://github.com/anthropics/skills

---

## 5. CrewAI

**Core abstraction:** `Crew` = collection of `Agent`s executing `Task`s under a `Process` (sequential or hierarchical). Each Agent has a role/goal/backstory triad. A newer `Flow` abstraction is event-driven for non-linear orchestration.

**Strengths:** Lowest-code path to "research agent + writer agent + reviewer agent." Role/goal/backstory prompting template is genuinely effective for simple pipelines. Planning agent and short/long/entity memory are built in. 34k+ stars, lots of tutorials.

**Weaknesses:** Opinionated to the point of rigidity. Every sharp edge — streaming, custom loops, token accounting — requires fighting the framework. Hierarchical process spawns a "manager" LLM call that's often a tax, not a benefit. Observability is thin outside CrewAI's paid platform.

**Pick when:** You want a demoable multi-role pipeline this afternoon and don't plan to operate it for years.

**Skip when:** Production longevity matters. The abstraction leaks fast.

Docs: https://docs.crewai.com — Repo: https://github.com/crewAIInc/crewAI

---

## 6. AutoGen / AG2 / Microsoft Agent Framework

**Core abstraction (AutoGen/AG2):** *Conversable agents.* Agents talk to each other via message passing. `GroupChat` with a speaker-selector resolves turn-taking. AG2 (community fork after creators left Microsoft in late 2024) is the actively maintained branch.

**Status:** Microsoft put AutoGen into maintenance mode in late 2025 and ships **Microsoft Agent Framework (MAF) 1.0** as the successor — enterprise-ready, stable APIs, .NET + Python, tight Azure AI Foundry integration. If you want the lineage on a supported stack, use MAF. If you want OSS community drive, use AG2.

**Strengths:** GroupChat is the cleanest "let N agents debate and converge" primitive. Event-driven v0.4 rewrite is legitimately async-first. MAF brings OpenTelemetry, observability, and a workflow engine.

**Weaknesses:** Multi-agent conversations burn tokens fast — every turn re-reads everyone else's turns. Debugging emergent conversational behavior is hard. Fragmentation (MS vs AG2 vs old 0.2) is confusing.

**Pick when:** Research-style debates, simulation, or when Azure governance is a requirement (MAF).

Repos: https://github.com/microsoft/autogen — https://github.com/ag2ai/ag2 — MAF: https://learn.microsoft.com/en-us/agent-framework/overview/

---

## 7. Letta (ex-MemGPT)

**Core abstraction:** Agent-as-OS. The LLM has tool calls for editing its own memory. Three tiers: **core memory** (small, in-context blocks the agent rewrites), **recall memory** (searchable conversation history), **archival memory** (vector-store tool calls). Letta runs as a server; agents are persistent records.

**Strengths:** The only framework where memory is a first-class, self-managed primitive — not a RAG bolt-on. Blocks-as-scratchpad is a genuinely good idea for long-lived personal assistants. Server/REST model makes agents survive client restarts naturally.

**Weaknesses:** Server-first architecture is heavy for single-user use. Memory tools burn output tokens constantly. Opinionated data model — if your memory shape doesn't match blocks/recall/archival, you fight it.

**Pick when:** Long-running personal agent where memory is the product (the agent "learns you"). **Inspiration for Conexus:** memory-block editing is a pattern worth stealing conceptually — the wiki is effectively our archival tier, but core-memory-as-editable-block could be a lightweight add (see Verdict).

Docs: https://docs.letta.com — Repo: https://github.com/letta-ai/letta

---

## 8. smolagents (HuggingFace)

**Core abstraction:** `CodeAgent` — the agent writes **Python code** as its action, not JSON tool calls. The code runs in a sandbox (E2B, Docker, Pyodide/Deno WASM). `ToolCallingAgent` exists for the classic JSON path. Entire core is ~1000 LOC.

**Strengths:** Code-as-action is measurably better — HF reports ~30% fewer LLM steps and 44% GAIA vs. 7% for GPT-4-turbo with JSON tools. Model-agnostic via LiteLLM. Hub sharing for tools/agents. Multimodal inputs supported.

**Weaknesses:** Sandboxing is a real operational dependency. Debugging emitted code is debugging LLM output. No built-in state durability, no multi-agent orchestration beyond managed sub-agents.

**Pick when:** Tasks that need **composition** of tool calls (scraping + parsing + math) where JSON tool-calling forces ugly N-step loops. Also: when you want to read the entire source in an afternoon.

Repo: https://github.com/huggingface/smolagents — Blog: https://huggingface.co/blog/smolagents

---

## 9. PydanticAI

**Core abstraction:** `Agent[Deps, Output]` — fully generic. `Deps` is a typed context object passed to every tool and prompt. `Output` is a Pydantic model the LLM must satisfy. Tools are decorated Python functions whose signatures become JSON schemas. Streaming supports partial structured output.

**Strengths:** The Pydantic team wrote it; schema generation is best-in-class. Type-checked end-to-end — your IDE knows what a tool returns. Model-agnostic (OpenAI, Anthropic, Gemini, Bedrock, Ollama, LiteLLM, 25+ providers). Simple, readable runtime. Hit 1.x in late 2025 and stable.

**Weaknesses:** No built-in durable state (though graph/workflow addons exist). No opinion about multi-agent — you wire it. Ecosystem smaller than LangChain's (but growing fast).

**Pick when:** You want rigor — typed state, strict outputs, minimal magic — in a Python codebase that already uses Pydantic. **Closest philosophical match to what Conexus is doing** (typed tool methods, Pydantic-parsed SKILL.md).

```python
from pydantic_ai import Agent
agent = Agent("anthropic:claude-sonnet-4-5", deps_type=AppCtx, output_type=ReportModel)

@agent.tool
def search_wiki(ctx: RunContext[AppCtx], query: str) -> list[str]: ...
```

Docs: https://ai.pydantic.dev — Repo: https://github.com/pydantic/pydantic-ai

---

## 10. Mastra

**Core abstraction:** TypeScript-first. `Agent` + `Workflow` (event-driven step graph) + RAG primitives + unified model router (3300+ models). Hit 1.0 in January 2026.

**Strengths:** If you're a full-stack TS shop, Mastra eliminates the Python-for-AI / TS-for-app split. Workflows are well-designed (steps, suspension, typed IO). From the Gatsby team — DX is polished. Excellent deploy story (Cloudflare Workers, Vercel, Node).

**Weaknesses:** TypeScript only. TS LLM ecosystem is maturing but still behind Python for research-grade tooling (DSPy, fine-tuning, evals). Not relevant for Conexus, but important landscape marker.

**Pick when:** Your entire product is TypeScript and Python feels foreign. Otherwise skip.

Docs: https://mastra.ai/docs — Repo: https://github.com/mastra-ai/mastra

---

## 11. DSPy

**Core abstraction:** Not a runtime — a **compiler**. You declare `Signature`s (typed input/output), compose them into `Module`s, and an **optimizer** (MIPROv2, COPRO, GEPA, BootstrapFewShot, BetterTogether) searches over prompts and/or weights against a metric on a trainset. The compiled program is deterministic Python.

**Strengths:** Only framework that treats prompts as something to *learn*, not craft. Optimizers genuinely move benchmarks. The signature-based API ages well — you're not re-doing the prompt when the model changes; you recompile. Stanford pedigree, serious research cadence.

**Weaknesses:** Mental-model cost is real. Needs a metric and a trainset — without them, DSPy is just a verbose wrapper. Not an agent *runtime* per se; you'd pair it with something else for tool loops (though `dspy.ReAct` exists).

**Pick when:** You have a measurable task (classification, extraction, multi-hop QA) and want your prompts optimized rather than authored. **Takeaway for Conexus:** even without adopting DSPy, the discipline of "every agent step has a metric" is worth internalizing.

Docs: https://dspy.ai — Repo: https://github.com/stanfordnlp/dspy

---

## 12. Agno (ex-Phidata)

**Core abstraction:** `Agent` with memory + knowledge + tools + reasoning, composable into `Teams` (role-coordinated) and `Workflows` (sequential/parallel). Rebranded from Phidata in Jan 2025; 39k+ stars.

**Strengths:** Claims ~2µs agent instantiation and ~3.75 KiB per agent (vs LangGraph's allegedly larger footprint). Multi-modal is first-class (text/image/audio/video). Ships with its own app/API runtime and monitoring UI. Fast iteration.

**Weaknesses:** "Batteries everywhere" posture similar to CrewAI — lots of defaults you may not want. Microbenchmarks (µs instantiation) are not the bottleneck in real agent runs (model latency is). Opinionated storage/monitoring that may compete with yours.

**Pick when:** Multi-modal agent (vision + audio) on a Python stack and you want a ready-made app+API layer. Overkill for a Telegram bot.

Docs: https://docs.agno.com — Repo: https://github.com/agno-agi/agno

---

## 13. LlamaIndex Agents (Workflows 1.0 / AgentWorkflow)

**Core abstraction:** **Workflows** — event-driven, async-first step graph. Steps are methods decorated with `@step`; they consume and emit typed events. State is carried via a `Context` object. `AgentWorkflow` is a pre-built workflow for agent loops; `AgentClient Protocol` (ACP) integrations added in 2026.

**Strengths:** Event-driven model is cleaner than graph-node-edges for many pipelines — a step just declares which event types it handles. Natural fit for RAG pipelines (LlamaIndex's home turf). Lightweight, FastAPI-friendly. Async-first with pause/resume.

**Weaknesses:** If you don't need RAG, you're dragging in a lot of retrieval machinery. Two abstractions (legacy `Agent` classes vs Workflows) still coexist; docs drift.

**Pick when:** Retrieval is central (document agents, multi-hop RAG), and you want agent loops in the same framework.

Docs: https://www.llamaindex.ai/workflows — Repo: https://github.com/run-llama/llama_index

---

## 14. Pocketflow (and minimalist frameworks)

**Core abstraction:** A graph of `Node`s connected by edges. Total framework: ~100 lines of Python. Zero dependencies.

**Strengths:** You can read it in one sitting. Zero lock-in. Excellent teaching tool and excellent starting point if you plan to fork. Ports exist in TS/Go/Rust/Java/C++/PHP/Ruby.

**Weaknesses:** Everything is DIY. No streaming, no checkpointing, no observability, no multi-agent primitives — you write them.

**Pick when:** You are building your own framework (like Conexus) and want a reference. The right posture is: **read Pocketflow, keep the philosophy, write your own primitives tailored to your stack.**

Repo: https://github.com/The-Pocket/PocketFlow

---

## Comparison Matrix

| Framework | Language | State model | Multi-agent | Memory built-in | MCP | Streaming | Prod-ready | Best for |
|---|---|---|---|---|---|---|---|---|
| LangChain | Py/TS | Stateless chains | Via LangGraph | RAG-style | Yes | Yes | Yes (legacy) | Integrations / RAG glue |
| LangGraph | Py/TS | **Checkpointed graph** | Yes | Via state | Yes | Yes | **Yes** | Durable, HITL, cycles |
| OpenAI Agents SDK | Py/TS | In-process loop | **Handoffs** | No | Yes | Yes | Yes | Handoff-style multi-agent |
| Claude Agent SDK | Py/TS | Messages + context edit | Sub-agents | Context-editing | Yes | Yes | Yes | Claude-native + Skills |
| CrewAI | Py | Process (seq/hier) | **Roles/crews** | Short/long/entity | Yes | Partial | Mid | Quick role pipelines |
| AutoGen / AG2 | Py | Conversation | **GroupChat** | Minimal | Yes | Yes | AG2 yes / AutoGen maint. | Debate / simulation |
| MS Agent Framework | Py/.NET | Workflows | Yes | Via store | Yes | Yes | **Yes (1.0)** | Azure enterprise |
| Letta | Py (server) | **Persistent agent** | Yes | **Self-editing blocks** | Yes | Yes | Yes | Long-lived personal agents |
| smolagents | Py | Code-loop | Sub-agents | No | Yes | Yes | Yes | Code-as-action tasks |
| PydanticAI | Py | Typed run | Manual | Via deps | Yes | **Typed** | **Yes** | Typed, rigorous pipelines |
| Mastra | **TS** | Workflow steps | Yes | Built-in | Yes | Yes | Yes | Full-stack TS apps |
| DSPy | Py | Compiled program | Via modules | N/A | Partial | Partial | Yes | Optimized prompts |
| Agno | Py | Agent/team/workflow | Yes | Built-in | Yes | Yes | Yes | Multi-modal, batteries |
| LlamaIndex Workflows | Py | **Event-driven** | AgentWorkflow | RAG-first | Yes | Yes | Yes | RAG-centric agents |
| Pocketflow | Py (+ports) | Graph | DIY | DIY | DIY | DIY | No (toolkit) | Reference / fork base |

---

## Verdict for Conexus

Conexus's profile: **Python, long-running, multi-agent, git-backed markdown wiki as second brain (not agent-facing RAG), cheap ops, LiteLLM, SQLite, APScheduler, Telegram, single operator.** The framework that fits exactly does not exist — which is why you're building one. What to steal:

1. **From Claude Agent SDK — the Skills pattern.** You already have `SKILL.md` with YAML frontmatter. Keep going. Lean harder into progressive disclosure: **the frontmatter should be the only thing in the system prompt by default**, body loaded on demand via a `read_skill_section` tool. This is the single best idea in the 2026 landscape and it is free to adopt.

2. **From LangGraph — checkpointing, not the graph.** You do not need a `StateGraph`. You *do* need SQLite-backed checkpointing on your tool-call loop: every turn, persist `(thread_id, step, messages, tool_results)` before the next LLM call. You get crash-safety and time-travel for free. Your existing `ping_log` idempotency pattern is already halfway there — generalize it.

3. **From OpenAI Agents SDK — handoffs, not a router.** When Ana needs Pesquisador's help, model it as a tool the LLM chooses (`handoff_to_pesquisador(query)`), not a classifier. The SDK's insight — "handoff is just a tool with special semantics" — keeps your `AgentRegistry` dispatch clean. Use their tracing ergonomics as inspiration for your `UsageTracker` span model.

4. **From PydanticAI — typed tools and dependencies.** Your `Tools` class with typed methods already follows this. Formalize `Deps` — a typed context object (DB, wiki, LLM, scheduler) passed into every tool — so tests don't fake globals. Auto-generate schemas from signatures (you do) and treat output parsing with Pydantic models for any structured tool return.

5. **From Letta — self-editing core memory.** Your wiki is archival. What you *don't* have is **core memory per agent** — a small, always-in-context block the agent can rewrite (e.g. "Leandro is on vacation until the 20th", "current project: Conexus", "last checkpoint: wiki sync at 08:00"). Add a `core_memory` table in SQLite + two tools (`core_memory_append`, `core_memory_replace`). Budget it at ~2KB per agent. This is the single highest-leverage memory upgrade available.

6. **From DSPy — metrics discipline, not the compiler.** Don't adopt DSPy. Do steal its posture: every agent capability should have a one-line metric (did the wiki commit land? did the reminder fire on time? did the article compile without citation errors?). Log those alongside cost in `UsageTracker`. Without metrics, "improving the agent" is vibes.

7. **From Pocketflow — the minimalism.** Resist the temptation to add abstractions Conexus doesn't need. You are building a two-agent bot on a Fly VM. If a primitive isn't earning its line count, delete it. The framework you want is probably <2000 lines of your own Python.

**What to ignore:** CrewAI (roles-and-backstories prompting is not your problem), Agno/Phidata (batteries you won't use), Mastra (wrong language), AutoGen (dead), raw LangChain (legacy weight). LangGraph is tempting and the patterns are right, but adopting it wholesale means a rewrite and a heavy dependency for two agents that fit in one process.

**The synthesis:** Conexus = PydanticAI-style typed tools + Claude-SDK-style Skills + LangGraph-style SQLite checkpointing + OpenAI-SDK-style handoffs + Letta-style core-memory blocks + wiki-as-archival + APScheduler-as-proactive-loop. That is a coherent framework and none of it requires importing any of these libraries. Build it, keep it under 2kLOC, and the wiki you're writing right now is the second half of the product.

---

## Citations

- LangChain 1.0 deprecation: https://python.langchain.com/docs/concepts/lcel/
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph interrupts: https://deepwiki.com/langchain-ai/langgraph/4.1-checkpointing-architecture
- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
- OpenAI Agents handoffs: https://openai.github.io/openai-agents-python/handoffs/
- OpenAI Agents guardrails/tracing: https://openai.github.io/openai-agents-python/guardrails/ — https://openai.github.io/openai-agents-python/tracing/
- Claude Agent SDK: https://code.claude.com/docs/en/agent-sdk/overview
- Agent Skills overview: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Skills engineering post: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Anthropic skills repo: https://github.com/anthropics/skills
- CrewAI: https://docs.crewai.com/en/concepts/tasks — https://github.com/crewAIInc/crewAI
- AutoGen: https://github.com/microsoft/autogen
- Microsoft Agent Framework 1.0: https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/
- Letta: https://github.com/letta-ai/letta — https://docs.letta.com/concepts/letta/
- Letta memory blocks: https://www.letta.com/blog/memory-blocks
- smolagents: https://github.com/huggingface/smolagents — https://huggingface.co/blog/smolagents
- PydanticAI: https://ai.pydantic.dev — https://github.com/pydantic/pydantic-ai
- Mastra: https://mastra.ai/docs — https://github.com/mastra-ai/mastra
- DSPy: https://dspy.ai — https://github.com/stanfordnlp/dspy
- DSPy optimizers: https://dspy.ai/learn/optimization/optimizers/
- Agno: https://github.com/agno-agi/agno — https://www.agno.com/
- LlamaIndex Workflows 1.0: https://www.llamaindex.ai/blog/announcing-workflows-1-0-a-lightweight-framework-for-agentic-systems
- LlamaIndex AgentWorkflow: https://www.llamaindex.ai/blog/introducing-agentworkflow-a-powerful-system-for-building-ai-agent-systems
- Pocketflow: https://github.com/The-Pocket/PocketFlow
