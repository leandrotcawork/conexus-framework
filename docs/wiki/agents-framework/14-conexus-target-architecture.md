# 14 — Conexus Target Architecture

> Audience: Leandro + Claude. This is the blueprint for kernel work (Phases 0–5). Companion to
> [[13-conexus-gap-analysis]] (the north-star punch list) and the twelve research partitions before it.
> **For Phases 6–9 (framework/consumer split, SKILL_PACK, TEAM_PACK, MCPProducer) see the
> v2 spec:** `docs/superpowers/specs/2026-04-29-conexus-framework-v2.md`.
> File paths are absolute-within-repo; signatures are sketches, not final API.

---

## 1. Executive summary

**Vision.** Conexus becomes a *thin, observable, cache-aware personal agent kernel* — a ~2 kLOC Python runtime over LiteLLM with SQLite + a git-backed markdown wiki as the default substrate, instrumented from day 1, evaluated in CI, and shaped so the patterns that matter in 2026 (progressive disclosure, prompt caching, Mem0-style consolidation, tool indexing, MCP interop) slot in as additions rather than rewrites. The contract stays what it is today: `SKILL.md` + `Tools` class + one handler loop. Everything else is substrate.

After the plan in this document is executed, Conexus is:

- A **kernel under 2 kLOC** with one tool-calling loop, one registry, one budget path, one usage tracker, and one tracer — no framework lock-in.
- **Cache-aware by construction**: stable prefix (system + tools + stable facts), timestamps in the trailing user message, `cache_control` breakpoints logged and metered, cache-hit ratio a first-class KPI.
- **Observable end-to-end**: every turn has a `trace_id`; every LLM call and tool call is a span; OTel GenAI conventions at the wire; Langfuse (self-hosted) or SQLite as the span store.
- **Evaluated on every push**: a promptfoo + DeepEval golden set gates merges. New prompts don't ship blind.
- **Memory-layered, not memory-flat**: short-term (rolling summary), episodic (turn log), semantic (BM25 + sqlite-vec hybrid wiki retrieval with optional rerank), procedural (`SKILL.md`), consolidated nightly by a sleep-time job.
- **Multi-agent substrate in place (Phase 8)**: `Handoff`, `HandoffRouter`, `BudgetCascader`, `TeamRegistry`, and `handoff_audit` are shipped; the supervisor execution loop and `trace_id` propagation are the remaining gaps before live cross-agent execution.
- **Interoperable at the edges**: an `MCPAdapter` so `AgentRegistry` can expose tools to Claude Desktop, and so external MCP servers (search, fetch, filesystem) can be consumed without bespoke code.

---

## 2. Design principles

1. **Keep the kernel under 2 kLOC.** A solo operator needs every line to fit in one head; framework bloat is the enemy of iteration speed.
2. **`SKILL.md` is the contract.** Models, tools, schedules, budgets, persona all live in one declarative file per agent — Python is how behaviour is enabled, not how agents are defined. ([[02-frameworks-survey §"declarative skill"]], [[05-skills-prompts]].)
3. **SQLite + git-backed wiki are the default, not defaults-to-replace.** One process, one volume, one `conexus.db`, one `/data/wiki`. Postgres/vector-DB/graph-DB only unlock when the deployment shape changes. ([[04-memory-systems §13]], [[10-deployment-runtime §8]].)
4. **MCP at the edges, native tools at the core.** Hot-path tools (`wiki_search`, `calendar_list_events`) stay in-process for latency and type-safety; MCP is the interop boundary for Claude Desktop and third-party servers. ([[11-mcp]].)
5. **Prompt cache is load-bearing.** Every change to `handle_agent_message` is judged by "does this keep the stable prefix stable?". The cache is not an optimisation — it is a correctness concern for the bill. ([[12-cost-token-optimization §3]].)
6. **Observability is a day-1 feature.** `trace_id` propagates before the first new feature ships. You cannot optimise what you cannot see, and you cannot debug production from SQLite `LIKE` queries. ([[09-observability-evals §2]].)
7. **Fail loud at startup, never at runtime.** Schema gen raises on unknown types; skill loader raises on missing budget fields; router raises on unknown model. Runtime stack traces are always better than silent string fallbacks. ([[13 §4.3]].)
8. **Tool outputs are paginated, not truncated.** An opaque `page_cursor` is the contract; `"…[truncado]"` is a bug. ([[12 §5]].)
9. **Every LLM call goes through `TrackedLLM`.** No direct `litellm.acompletion`. Voice transcription is a call too. This is the invariant the usage tracker, the budget cap, and the tracer all depend on.
10. **Scheduled jobs are forensic artifacts.** `ping_log` is tri-state (`pending`/`sent`/`failed`), every job writes an audit row, no at-least-once drift into at-most-once by accident.
11. **Agents don't execute handoffs yet, but the substrate is in place.** Phase 8 shipped `Handoff`, `HandoffRouter`, `TeamRegistry`, `BudgetCascader`, and `handoff_audit`. What remains is the execution loop that drives `handle_agent_message` per hop and wires real agents into a live `TEAM_PACK`. `trace_id` propagation across hops is still pending.
12. **Git is the undo log.** Wiki writes are commits; memory consolidation is a commit; audit is `git log`. We do not build a parallel history store.

---

## 3. Target architecture diagram

```
                         ┌───────────────────────────────────────┐
                         │            Telegram (Ana)             │
                         │         Telegram (Pesquisador)        │
                         │            /healthz (aiohttp)         │
                         └──────────────┬────────────────────────┘
                                        │
                  ┌─────────────────────▼──────────────────────┐
                  │              Agent Kernel                  │
                  │  ┌──────────────────────────────────────┐  │
                  │  │   handle_agent_message (one loop)    │  │
                  │  │     ├─ budget.check (pre + mid)      │  │
                  │  │     ├─ context.build (cache-aware)   │  │
                  │  │     ├─ TrackedLLM.acall              │  │
                  │  │     └─ AgentRegistry.execute_tool    │  │
                  │  └──────────────────────────────────────┘  │
                  │  CapChecker · UsageTracker · Tracer         │
                  │  ContextVar: context_tag · trace_id         │
                  └──┬──────────────┬─────────────┬─────────────┘
                     │              │             │
      ┌──────────────▼──────┐  ┌────▼──────┐  ┌───▼─────────────────────┐
      │     Memory          │  │   Tools   │  │     LLM layer           │
      │ ─ SqliteStore       │  │ schema_gen│  │ TrackedLLM (LiteLLM)    │
      │ ─ WikiStore         │  │ (Literal, │  │ ModelCascade (Flash→Pro)│
      │   · BM25 (rank_bm25)│  │  Enum,    │  │ cache_control injector  │
      │   · sqlite-vec opt. │  │  Pydantic)│  │ fallback chain          │
      │   · reranker (edge) │  │ MCPAdapter│  │ pricing + cache cost    │
      │ ─ RollingSummariser │  │ ToolIndex │  │ retries (tenacity)      │
      │ ─ MemoryConsolidator│  │ validator │  └─────────────────────────┘
      │   (APScheduler job) │  └───────────┘
      └─────────────────────┘
                     │
           ┌─────────▼──────────────────────────────────────────┐
           │                Runtime                              │
           │  ConexusScheduler (APScheduler, misfire+coalesce)   │
           │  BatchDispatcher (Gemini/Anthropic Batch APIs)      │
           │  catchup() on boot                                  │
           └─────────────────────────────────────────────────────┘
                     │
           ┌─────────▼──────────────────────────────────────────┐
           │             Observability                           │
           │  OTel GenAI spans → Langfuse (self-host) + SQLite   │
           │  tool_audit table · trace_checkpoints table         │
           │  EvalRunner (promptfoo + DeepEval, CI gate)         │
           └─────────────────────────────────────────────────────┘
```

---

## 4. Module-by-module target

### `core/agent_handler.py` — **evolves**
Stays: single loop, max_turns, fallback message, `chat_append(user)` before LLM.
Evolves:
- Remove timestamp concat from `cfg.system_prompt` build (kills cache). Timestamp goes in a trailing user-role message: `<now>2026-04-15T14:30-03:00</now>`. ([[13 §4.5]])
- Inject `trace_id` ContextVar at turn 0; thread it through every tool dispatch and LLM call.
- Mid-loop budget check: re-invoke `CapChecker.allow` after each tool call, not just at entry.
- On `max_turns` exhaustion, synthesise a *recap user message* and run one more turn with `tool_choice="none"` before bailing.
- New context builder `build_turn_context(cfg, store, user_msg) -> list[Message]` that emits messages in cache-stable order: system → tool schemas → stable facts (wrapped `<facts>`) → summary (wrapped `<summary>`) → last-N raw history → trailing user + `<now>`.

### `core/agent_registry.py` — **evolves**
Stays: uniform JSON return, exceptions caught as `{"error": ...}`.
Evolves:
- Write a row to new `tool_audit` table per call: `(trace_id, agent, tool_name, args_json, result_json, duration_ms, error, cache_hit)`.
- JSON serialisation uses `default=str`; coercions logged.
- Tool input validated against the generated schema before dispatch (`core/tools/validator.py`).
- Wraps each call in a `tool.call` OTel span.

### `core/tools/schema_gen.py` — **evolves** (bug + feature)
Stays: `inspect.signature` + `typing.get_type_hints` pipeline.
Evolves:
- Add `Literal[...]` → `enum`; `Enum` subclass → `enum`; `dict[str, X]` → `object+additionalProperties`; nested Pydantic models → `$ref`.
- Raise `UnsupportedTypeError` on truly-unknown types at startup — no string fallback. ([[13 §4.3]])
- Emit `strict: true` and `additionalProperties: false` at root.
- Parse Google-style docstrings for `description` fields; `_tool_schemas` ClassVar becomes optional.

### `core/tools/validator.py` — **new**
`validate_args(schema: dict, args: dict) -> dict` — `jsonschema` or `pydantic.TypeAdapter`-based, raises typed `ToolArgumentError` that `AgentRegistry` catches and returns as a structured tool error the LLM can recover from.

### `core/tools/mcp_adapter.py` — **new**
`class MCPAdapter`:
- `expose(registry: AgentRegistry) -> FastMCP` — publishes tools over stdio/SSE for Claude Desktop.
- `consume(server_url: str) -> list[ToolDef]` — registers remote MCP tools into `AgentRegistry` with automatic schema translation. ([[11-mcp §4]])

### `core/tools/tool_index.py` — **new, deferred until tool count > 20**
Tool-RAG per [[03-tools-design §"Toolshed"]]. Embeds tool names+descriptions; at turn-start picks top-K tools relevant to the user message and only those schemas land in context. Gated behind `AgentHandlerConfig.tool_index: bool`.

### `core/memory/sqlite_store.py` — **evolves**
Stays: facts, todos, chat_history, ping_log, llm_usage.
Evolves:
- `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL` on connect. ([[13 §4.10]])
- `ping_log` tri-state: `attempts INTEGER`, `failed_at`, `last_error`.
- New `trace_checkpoints` table: `(trace_id, turn_idx, assistant_text, tool_calls_json, ts)` — replay primitive.
- New `tool_audit` table (above).
- `chat_history` gains `conversation_summary` column (or sibling `session_summary` table keyed by session).
- `llm_usage` gains `cache_read_tokens`, `cache_write_tokens`, `cache_cost_usd`.

### `core/memory/wiki_store.py` — **evolves**
Stays: markdown, git commits, frontmatter, path-escape guard.
Evolves:
- Content-hash dedupe: read existing file, compare SHA256, skip commit if identical. ([[13 §5]])
- Async git push via `asyncio.to_thread` (don't block the reply).
- BM25 index (`rank_bm25`) rebuilt on each write; intro + section chunking; frontmatter metadata filters. ([[07-rag-and-wiki §"Phase A"]])
- Optional `sqlite-vec` embeddings populated on write; hybrid BM25+dense via RRF; cross-encoder rerank as a pluggable edge function.
- New `search(query, *, filters, top_k, rerank=False) -> list[Chunk]` replaces substring-match.

### `core/memory/rolling_summariser.py` — **new**
See §8.

### `core/memory/consolidator.py` — **new**
Nightly APScheduler job; Mem0-style ADD/UPDATE/DELETE over recent chat_history against the wiki. See §8.

### `core/llm/router.py` — **evolves**
Stays: LiteLLM wrapping, tenacity retries, fallback chain.
Evolves:
- Inject `cache_control` breakpoints on system + tool schemas + stable facts per provider semantics (Anthropic explicit; OpenAI implicit passthrough; Gemini `CachedContent` opt-in). ([[12 §3]])
- Return cache-read/write token counts; pass them through to `UsageTracker`.
- `ModelCascade` helper for Flash→Pro escalation (see §8).

### `core/llm/usage_tracker.py` — **evolves**
Adds cache columns, `trace_id` column, `/uso` breakdown by trace and by cache-hit ratio.

### `core/llm/context_tag.py` — **evolves**
Adds `trace_id: ContextVar[str | None]` alongside existing `context`.

### `core/llm/pricing.py` — **evolves**
Adds cache-read/write unit prices per model; `ModelCascade` uses pricing for escalate/de-escalate decisions.

### `core/budget/cap_checker.py` — **evolves**
Stays: pre-call check, notify/halt.
Evolves: mid-loop re-check; per-job `BudgetCap` (separate from reactive cap) for `compile_article`-class jobs. ([[13 §5]])

### `core/scheduler/scheduler.py` — **evolves**
Stays: cron strings from `SKILL.md`, `catchup()`.
Evolves: per-job `misfire_grace_time` + `coalesce`; keep in-memory job-store (SKILL.md re-registers on boot is fine) but standardise the misfire policy per job kind.

### `core/health.py` — **new**
Tiny aiohttp `/healthz` checking LLM router, SQLite SELECT 1, wiki volume writable.

### `core/tracer.py` — **new**
See §8.

### `core/evals/runner.py` — **new** (and `evals/` directory)
See §8.

### `core/team/` — **new (Phase 8, shipped)**

The scaffold landed as a full team substrate, not just a `Handoff` model. Key modules (all under `src/conexus/core/team/`):

- `handoff.py` — frozen `Handoff` Pydantic model with hop tracking, taint propagation fields, and `next_hop()`.
- `team_pack.py` — `TeamPackFrontmatter` / `TeamBudget` / `TeamPolicy` + `parse_team_pack()`.
- `team_loader.py` — `TeamLoader(available_agents).load(pack_path)` validates members, manager, and budget shares.
- `team_registry.py` — runtime view: `members`, `manager`, `policy`, `budget`, `edges_from()`.
- `handoff_router.py` — `HandoffRouter.route(handoff)` with 4-step resolution.
- `budget_cascader.py` — `BudgetCascader` with `notify` / `halt_member` / `borrow_from_pool`.

Audit: `src/conexus/core/memory/handoff_audit.py` — `handoff_audit` SQLite table.

The `core/handoff.py` path described in the original §8 spec was not used; the implementation landed under `core/team/handoff.py` instead.

### `main.py` — **evolves**
Stays: skill → LLM → tools → registry → bot wiring.
Evolves: de-duplicate hard-coded "REGRA CRÍTICA" / "PROTOCOLO OBRIGATÓRIO" appendages — move them into `SKILL.md` bodies. Fix UTF-8 bug at `main.py:263`. Route voice transcription through `TrackedLLM`.

### `agents/ana/`, `agents/pesquisador/` — **stay, mostly**
SKILL.md bodies absorb the protocol text previously in `main.py`. Pesquisador's `compile_article` output cap drops to 8k; prompt template moves to `agents/pesquisador/prompts/compile_article.md`. `web_fetch` gets an SSRF guard; eventually (Phase 4) replaced by MCP client to `@modelcontextprotocol/server-fetch`.

---

## 5. What we steal, from which framework

| Pattern | From | Why it fits Conexus |
|---|---|---|
| **Core-memory blocks** (always-in-context, agent-editable) | Letta / MemGPT | `facts` namespace `core:` injected verbatim in system prompt; adds self-editing without adopting Letta's runtime. ([[04 §4]]) |
| **Handoff-as-tool** (typed `transfer_to_<agent>`) | OpenAI Agents SDK | Clean multi-agent primitive that layers on top of our existing `AgentRegistry` dispatch — no runner rewrite. ([[06-multi-agent-orchestration §"handoffs"]]) |
| **Progressive disclosure** (load skills on-demand, not eagerly) | Anthropic Skills | Our `tools:` allowlist already does this for tools; we extend to sub-skills (`agents/ana/skills/calendar.md`) loaded on intent detection. ([[05-skills-prompts]]) |
| **Checkpointer pattern** (state snapshot per step) | LangGraph | Not LangGraph itself — just the *table shape*: `trace_checkpoints(trace_id, turn_idx, ...)`. Gives replay + post-mortem without the graph runtime. ([[02 §2]]) |
| **DSPy metrics / optimisers** | DSPy | `EvalRunner` uses DSPy-style metrics (`exact_match`, `llm_as_judge`, `answer_relevance`) without adopting the optimiser — optimiser is a later move if evals become load-bearing. ([[09 §"evals"]]) |
| **Planner/executor split** (plan JSON first, then act) | ReWOO | Gated per-context: `compile_article` uses plan-first; reactive Ana stays ReAct. ([[08-planning-reasoning §"ReWOO"]]) |
| **Tool-RAG** (top-K relevant tool schemas per turn) | Toolshed | Deferred behind a flag; lands when tool count crosses 20 and per-turn tool-schema tokens cross 5 k. ([[03 §"Tool-RAG"]]) |
| **Batch API for non-urgent jobs** (50% off, 24 h SLA) | Anthropic / Gemini Batch | Morning briefing and recap are wall-clock loose; `BatchDispatcher` submits them to the provider batch endpoint. ([[12 §4]]) |
| **Mem0 ADD/UPDATE/DELETE extractor** | Mem0 | Runs as nightly `MemoryConsolidator` over yesterday's `chat_history` with the current wiki as grounding; commits its edits to the wiki (git as audit). ([[04 §5]]) |
| **Bitemporal fact edges** | Zep / Graphiti | Borrow only the `invalidated_at` column on wiki frontmatter; not the graph runtime. Enough for "what did Ana believe on March 3?". ([[04 §6]]) |
| **Guardrails-AI validators** | Guardrails-AI | Tool output validators (Pydantic) at the registry boundary. ([[09 §"guardrails"]]) |
| **OTel GenAI conventions** | OpenTelemetry | Wire format for spans; Langfuse and SQLite both ingest it. Future backend swap is free. ([[09 §3]]) |

---

## 6. What we deliberately DON'T adopt

- **Postgres.** One-process SQLite on the Fly volume is correct until locked-errors appear or a second operator wants an instance. Neither applies. ([[10 §11]])
- **LangGraph runtime.** We steal the checkpointer *shape*, not the graph. Graph overhead pays off at HITL + durable-workflow thresholds that Conexus doesn't cross. ([[02 §2]])
- **Letta runtime.** Letta owns the agent runtime; we already own ours. Taking it means throwing out `handle_agent_message`. Instead, borrow the core-block concept as a `facts` namespace. ([[04 §4]])
- **CrewAI / AutoGen / MAF.** Role-based crews only pay off with 3+ specialist agents and orchestration complexity we don't have.
- **Full GraphRAG / Zep / Neo4j.** Bitemporal KG is overkill for a single-user personal agent; file-level frontmatter is sufficient.
- **Real multi-agent today.** Two isolated peers by design; only `trace_id` + `Handoff` scaffold lands preemptively.
- **Managed vector DB (Pinecone, Weaviate).** Violates the "one process, one volume" deployment shape. `sqlite-vec` stays in `conexus.db`.
- **HyDE.** Only adopt after measuring BM25+dense+rerank and finding a vocabulary gap. ([[07 §10]])
- **Streaming tool calls.** Telegram is final-message-only; no payoff.

---

## 7. Migration plan (phased, non-breaking)

Every phase ends with: all tests green, eval suite green, Fly deploy clean, KPI dashboard showing the improvement. No phase is permitted to break the SKILL.md contract.

### Phase 0 — Bug-fix sprint (1 week)

**Goal.** Clear the [[13 §6]] punch list top-10. Nothing fancy, just green lights before we start adding.

Changes:
- `core/agent_handler.py`: remove timestamp from system prompt; trailing `<now>` user message.
- `core/tools/schema_gen.py`: `Literal`/`Enum`/`dict`/Pydantic; raise on unknown; `strict: true` + `additionalProperties: false`.
- `agents/pesquisador/tools.py:web_fetch`: SSRF guard (scheme allowlist, private-IP blocklist, no-redirect-to-private).
- `core/memory/sqlite_store.py`: `PRAGMA journal_mode=WAL; synchronous=NORMAL`; tri-state `ping_log` with `attempts`/`failed_at`/`last_error`.
- `core/memory/wiki_store.py`: UTF-8 handling verified; content-hash dedupe on write.
- `core/messaging/telegram_bot.py:178`: route voice transcription through `TrackedLLM`.
- `main.py:263`: UTF-8 `â€"` bug fixed; protocol text moved to `SKILL.md` bodies.
- `agents/pesquisador/tools.py:compile_article`: cap at 8k output; per-job `BudgetCap`.

Files touched: `core/agent_handler.py`, `core/tools/schema_gen.py`, `core/memory/{sqlite,wiki}_store.py`, `core/messaging/telegram_bot.py`, `core/budget/cap_checker.py`, `agents/pesquisador/*`, `main.py`.

Acceptance:
- No regression in existing tests.
- New unit tests for `schema_gen` covering `Literal`/`Enum`/`dict`/unknown-raises.
- Manual smoke: morning briefing runs end-to-end; Ana reactive turn shows measurably lower input tokens on `/uso`.

Effort: **~5 days.**

### Phase 1 — Observability + evals foundation (1.5 weeks)

**Goal.** See what the agents do, prove changes don't regress.

Changes:
- `core/llm/context_tag.py`: add `trace_id` ContextVar.
- `core/tracer.py`: new (see §8). OTel GenAI span emitter; SQLite + optional Langfuse backend.
- `core/agent_handler.py`, `core/agent_registry.py`, `core/llm/router.py`: wrap with spans; propagate `trace_id`.
- `core/memory/sqlite_store.py`: new `tool_audit` table; `llm_usage.trace_id` column.
- `core/evals/runner.py`: new (see §8). Promptfoo YAML + DeepEval-style metrics. Golden set under `evals/golden/`.
- GitHub Action lane: `uv run python -m core.evals.runner --gate`.

Files touched: `core/tracer.py` (new), `core/evals/*` (new), `evals/` (new), `core/llm/*`, `core/agent_handler.py`, `core/agent_registry.py`, `.github/workflows/evals.yml`.

Acceptance:
- `/uso` shows trace-level breakdown.
- Every turn produces a tool_audit trace readable by `trace_id`.
- Golden set of 20 scenarios runs in CI; merge gate enforced.
- Cache-hit ratio KPI visible (even if 0% pre-Phase 3).

Effort: **~8 days.**

### Phase 2 — Memory upgrade (2 weeks)

**Goal.** Retrieval that survives past 50 wiki articles and 10 chat messages.

Changes:
- `core/memory/rolling_summariser.py`: new (see §8). Fires every 20 turns; writes `sessions.summary`.
- `core/memory/wiki_store.py`: BM25 via `rank_bm25`; frontmatter-aware chunking; `search(query, *, filters, top_k)` new signature.
- Optional: `sqlite-vec` extension loaded; embeddings on write; RRF fusion; cross-encoder rerank via Gemini or local BGE.
- `core/memory/consolidator.py`: new Mem0-style nightly job; ADD/UPDATE/DELETE via `wiki_write`/`wiki_delete`; `invalidated_at` frontmatter on superseded facts.
- `agents/ana/jobs.py`, `agents/pesquisador/jobs.py`: register consolidator.

Files touched: `core/memory/*`, `agents/*/jobs.py`, `agents/*/tools.py` (new `wiki_search_semantic`), `pyproject.toml` (`rank-bm25`, optional `sqlite-vec`).

Acceptance:
- Memory eval harness (seeded facts, recall@5) in CI; target ≥ 80% at 200 facts.
- 100-turn Ana session uses < 2 k tokens for history context.
- Consolidator dry-run produces sensible diffs on a week of real chat_history.

Effort: **~10 days.**

### Phase 3 — Cost optimisation (1 week)

**Goal.** Make the cache do its job; halve briefing cost via Batch API.

Changes:
- `core/llm/router.py`: inject `cache_control` breakpoints per provider; pass through cache-token counts.
- `core/llm/usage_tracker.py`: `cache_read_tokens`, `cache_write_tokens`, `cache_cost_usd` columns.
- `core/llm/pricing.py`: per-model cache prices.
- `core/llm/cascade.py`: `ModelCascade.escalate_if(condition)` helper (Flash → Pro).
- `core/batch_dispatcher.py`: new; submits briefing + recap jobs to Gemini/Anthropic Batch API with 24 h SLA.
- Per-agent + per-model `BudgetCap` in `SKILL.md`.

Files touched: `core/llm/*`, `core/budget/*`, `core/batch_dispatcher.py` (new), `agents/*/SKILL.md`, `agents/*/jobs.py`.

Acceptance:
- Cache-hit ratio ≥ 60% on reactive Ana turns (visible in Phase 1 dashboard).
- Morning briefing daily cost falls ≥ 40% (Batch API + cache).
- Per-model budget cap actually fires in a test.

Effort: **~5 days.**

### Phase 4 — Tools evolution (1.5 weeks)

**Goal.** Structured outputs, interop, optional Tool-RAG.

Changes:
- `core/tools/validator.py`: JSON Schema validation pre-dispatch.
- Tool return types migrate to Pydantic models; registry validates on egress.
- `core/tools/mcp_adapter.py`: FastMCP wrapper around `AgentRegistry`; stdio + SSE transports.
- External MCP consumer for web search / web fetch — Pesquisador's bespoke tools become thin wrappers.
- `core/tools/tool_index.py`: scaffolded; off by default. Turned on for Pesquisador only if tool count crosses 20.

Files touched: `core/tools/*` (expanded), `agents/*/tools.py` (return types tightened), `pyproject.toml` (`mcp`, `fastmcp`).

Acceptance:
- Claude Desktop connects to Conexus MCP server and reads wiki.
- `web_search` replaced by MCP server; SSRF-guarded bespoke code deleted.
- Tool-output validation catches at least one previously-silent coercion error.

Effort: **~7 days.**

### Phase 5 — Multi-agent foundation (3–5 days, scaffold only)

> **Superseded by Phase 8.** The full substrate (`Handoff`, `HandoffRouter`, `TeamRegistry`, `BudgetCascader`, `handoff_audit`) shipped in Phase 8 under `src/conexus/core/team/`. What Phase 5 originally specified as a minimal scaffold is now a complete routing layer. What remains from Phase 5's intent is wiring the execution loop (calling `handle_agent_message` per hop) and `trace_id` propagation across agent boundaries.

**Original goal.** The contracts for future handoffs exist, so adding a third agent is YAML + one tool.

Remaining work:
- Supervisor execution loop: iterate `HandoffRouter.route()` → `handle_agent_message()` per hop, share `trace_id`.
- `ask_isaac` / `ask_pesquisador` as generated tools that produce a `Handoff` and enter the loop.
- Trace propagation: handoff spans parent to the originator's trace.

Effort: **~2 days** (substrate already in place).

> **Phases 0–5 above complete the kernel.** The v2 spec
> (`docs/superpowers/specs/2026-04-29-conexus-framework-v2.md`) picks up from here with:
>
> | Phase | Work | Status |
> |-------|------|--------|
> | 6 | Framework / consumer split — `conexus` becomes a pip package; Ana + Pesquisador become consumers | Done (commit 5c5162e) |
> | 7 | `SKILL_PACK` format + `TrifectaGuard` (deterministic taint check) + `ToolBackend` abstraction + MCP-stdio consume | **Done** (commit 80dba33 + 16f864f). See `src/conexus/core/skills/`, `src/conexus/core/trifecta/`, `src/conexus/core/backends/`. |
> | 8 | `TEAM_PACK` + `BudgetCascader` + `HandoffRouter` + cross-agent TrifectaGuard | **Done** (commits d476101–6235bc8). See `src/conexus/core/team/`, `src/conexus/core/memory/handoff_audit.py`. |
> | 9 | `MCPProducer` (bearer auth) — expose Conexus to Claude Code / Cursor | Future |
>
> This document governs Phases 0–5 only. The v2 spec governs Phases 6–9.

---

## 8. New primitives to add — short specs

### `RollingSummariser` — `core/memory/rolling_summariser.py`
```python
class RollingSummariser:
    def __init__(self, llm: TrackedLLM, store: SqliteStore, *, every: int = 20): ...
    async def maybe_refresh(self, session_id: str) -> str | None:
        """If chat_history for session_id grew by >= `every` since last summary,
        run a cheap Flash call that folds (old_summary + new_messages) into a new
        summary. Writes to sessions.summary and returns it (or None if not due)."""
```
Called by `handle_agent_message` *before* context build so the fresh summary lands in the cacheable prefix when possible.

### `MemoryConsolidator` — `core/memory/consolidator.py`
```python
class MemoryConsolidator:
    def __init__(self, llm: TrackedLLM, store: SqliteStore, wiki: WikiStore): ...
    async def run(self, *, since: datetime) -> ConsolidationReport:
        """Read chat_history since `since`, retrieve top-k relevant wiki chunks,
        ask LLM for ADD/UPDATE/DELETE operations, apply via wiki_write/wiki_delete,
        commit once per batch with message 'consolidate: YYYY-MM-DD'."""
```
Registered as nightly APScheduler job in each agent's `jobs.py` (different wikis).

### `Tracer` — `core/tracer.py`
```python
class Tracer:
    def start_turn(self, agent: str, user_msg: str) -> str: ...   # returns trace_id
    @contextmanager
    def span(self, name: str, **attrs): ...
    def emit(self, event: dict): ...                                # OTel GenAI fields
```
SQLite backend (`trace_spans` table) by default; Langfuse backend switched on via env.

### `EvalRunner` — `core/evals/runner.py`
```python
class EvalRunner:
    def __init__(self, suite_dir: Path, *, gate: bool = False): ...
    async def run(self) -> EvalReport:
        """Load YAML suites (promptfoo format), run each scenario through a
        frozen agent fixture, compute metrics (exact_match, tool_sequence_match,
        llm_as_judge), return per-metric pass/fail and regression deltas."""
```
Golden set under `evals/golden/{ana,pesquisador}/*.yaml`; CI gate fails on regression beyond tolerance.

### `ModelCascade` — `core/llm/cascade.py`
```python
class ModelCascade:
    def __init__(self, cheap: TrackedLLM, strong: TrackedLLM, *,
                 escalate_if: Callable[[ChatResponse], bool]): ...
    async def acall(self, messages, tools): ...
```
Wraps router-level fallback; used today by Pesquisador's Flash→Pro split. Escalation predicates: low-confidence heuristic, explicit tool request, length > threshold.

### `Handoff` — `src/conexus/core/team/handoff.py` (Phase 8, shipped)

The original spec sketch was superseded by the Phase 8 implementation. The actual model is:

```python
class Handoff(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: Literal["1"] = "1"
    from_agent: str
    to_agent: str         # "auto" triggers HandoffRouter
    payload: dict[str, Any] = Field(default_factory=dict)
    context_mode: Literal["full", "last_message", "summary"] = "summary"
    return_on: str | None = None
    hop_count: int = 0
    max_hops: int = 5
    tags: set[DataClass] = Field(default_factory=set)
    trust_boundary_cleared: bool = False
```

Carried on `AgentHandlerConfig.incoming_handoff`; `handle_agent_message` uses `TrifectaGuard.from_handoff()` when it is set.

### `MCPAdapter` — `core/tools/mcp_adapter.py`
See §4.

### `ToolIndex` — `core/tools/tool_index.py`
```python
class ToolIndex:
    def __init__(self, tools: dict[str, ToolDef], embedder): ...
    def top_k(self, query: str, k: int = 10) -> list[str]:
        """Return tool names whose description best matches query."""
```
Used by `handle_agent_message` only when `cfg.tool_index_enabled` is True.

---

## 9. Metrics we track from day 1

1. **Cache hit ratio** (input tokens served from cache / total input tokens) — per agent, per model.
2. **Cost per conversation** (sum of `llm_usage.cost_usd` grouped by `trace_id`).
3. **Cost per scheduled job** (grouped by kind).
4. **Tool-success rate** (tool_audit rows where `error IS NULL` / total).
5. **Tool-calls per turn** (median and p95).
6. **Mean turns per trace** (should stay ≤ 3 for reactive Ana).
7. **Wiki retrieval precision@5** — measured via the memory eval harness, not production.
8. **Eval regression rate** (scenarios failing vs. baseline) — must be 0 at merge.
9. **Context tokens used vs. budget** (fraction of max-context consumed per turn).
10. **Scheduler catchup lag** (seconds between scheduled fire and actual fire).
11. **Ping-log failure rate** (`failed_at IS NOT NULL` / total).
12. **Budget-cap trip count** (per agent per day).
13. **Trace-to-commit ratio** (wiki commits per 100 traces) — sanity on memory write volume.
14. **Model cascade escalation rate** (Flash→Pro escalations / total Pesquisador turns).
15. **Voice transcription cost** (now visible once routed through TrackedLLM).

All exposed via `/uso` extended and dumped nightly to a `kpi_daily` table.

---

## 10. Acceptance — "v1 kernel complete"

All of:

- [ ] Kernel LOC under 2 000 (excluding tests and agent code).
- [ ] `SKILL.md` contract unchanged from today — no agent code edits required for Phase 0–5 migrations.
- [ ] `schema_gen` raises on unknown types; all Ana + Pesquisador tools typed with `Literal`/`Enum` where semantic.
- [ ] Every turn has a `trace_id`; every LLM and tool call is a span; `trace_checkpoints` + `tool_audit` populated.
- [ ] Cache hit ratio ≥ 60% on reactive Ana measured over 7 days.
- [ ] CI eval gate active; ≥ 20 scenarios per agent; PRs blocked on regression.
- [ ] Wiki search uses BM25 + frontmatter filter; memory eval recall@5 ≥ 80% at 200 facts.
- [ ] Rolling summariser active; 100-turn session context cost bounded.
- [ ] `MemoryConsolidator` runs nightly, commits visible in `/data/wiki` git log.
- [ ] Morning briefing runs via Batch API; per-day cost falls ≥ 40% vs. pre-Phase 3 baseline.
- [ ] `/healthz` returns 200 with component statuses.
- [ ] MCP adapter exposes wiki to Claude Desktop end-to-end.
- [x] `Handoff` primitive + `HandoffRouter` + `BudgetCascader` + `handoff_audit` exist and are tested (Phase 8). Remaining: execution loop wiring two dummy agents end-to-end with shared `trace_id`.
- [ ] No `litellm.acompletion` call anywhere outside `TrackedLLM`.
- [ ] All 15 KPIs in §9 are queryable from SQLite.

When all boxes are ticked, v1 kernel is shipped and agent-specific bug-fix work resumes on top of a stable substrate.

---

## 11. Open questions

1. **Do we expose `WikiStore` via MCP?** Leaning yes (Claude Desktop memory review is the killer use-case) but it raises a write-safety question — do we expose `wiki_write` or just `wiki_search`+`wiki_read`?
2. **Rerank model: self-host BGE, or call Gemini/Cohere?** Self-host adds a dependency; hosted adds a hot-path latency + cost. Probably hosted for v1, self-host as Phase 6 if volume warrants.
3. **Keep LiteLLM, or direct SDK calls?** LiteLLM's fallback chain is useful but its cache-control passthrough is patchy. Might migrate `TrackedLLM` to direct `anthropic` + `google-genai` SDKs in Phase 6.
4. **`sqlite-vec` or wait for FTS5 + BM25 only?** Phase 2 leaves sqlite-vec optional. Decision gate: if memory eval recall@5 with BM25 alone stays ≥ 80% at 500 facts, skip vec entirely.
5. **Do we adopt Anthropic "Memory Tool" (the 2025 hosted tool)?** Tempting but it binds us to Anthropic; our wiki already does this better with git. Probably no.
6. **Langfuse self-host vs. OTel → nothing yet?** SQLite-only spans are sufficient for a solo operator; Langfuse is a second Fly app to run. Defer until an incident needs a replay UI.
7. **Do Pesquisador's article drafts become their own conversation threads?** If yes, we need proper `session_id` per research thread, not the Telegram-chat-id-as-session assumption Ana uses.
8. **Sleep-time core-block editor: separate agent or nightly job?** Phase 2 does it as a job. Letta does it as an agent. The job is cheaper; the agent generalises better. Revisit after 3 months of consolidation data.
9. **How do we version the eval golden set?** Git, obviously — but do we branch it per model version, or pin via `model@YYYY-MM-DD` in the suite YAML?
10. **MCP: stdio, SSE, or HTTP?** Stdio is the obvious pick for Claude Desktop; SSE unlocks web UIs later. Start stdio-only.

---

*This document is load-bearing for Phases 0–5. When an implementation decision contradicts it, either (a) update this doc first, then the code, or (b) reject the change. Link back here from every PR that implements a phase item. Last revised 2026-04-29.*
