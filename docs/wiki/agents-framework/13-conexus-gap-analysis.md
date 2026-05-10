# 13 — Conexus Gap Analysis vs. Agents Framework Wiki

> Rigorous walk-through of the current Conexus codebase against the twelve research partitions in `agents-framework/`. Audience: Leandro + Claude, reading this alongside the code. Not agent-facing. File paths are absolute-within-repo; line numbers reflect the commit of record.

---

## 1. Executive summary

- **Architecture is sound at the contract layer.** `SKILL.md` + `Tools` class + `handle_agent_message` matches the 2026 industry shape described in [[01-agent-fundamentals]] / [[02-frameworks-survey]]: declarative agent, auto-generated tool schemas, single reusable loop. The gaps are almost entirely in the *production-hardening* concerns — caching, observability, evaluation, retrieval quality.
- **The single biggest cost bug** was that `core/agent_handler.py` appended the current BRT timestamp into the system prompt on every call, killing prefix caching. **Resolved in PR2** ([fix/cluster-a-pr2-cache-control-and-ping-log](https://github.com/leandrotcawork/conexus-framework/pull/3)): timestamp removed from `handle_agent_message`; `BuiltinTimeTools.get_current_time` added as an on-demand tool (`src/conexus/core/tools/builtin_time.py`); `LLMService._apply_cache_control` stamps `ephemeral` `cache_control` on the system message and last tool schema (`src/conexus/core/llm/service.py:15-43`); `handle_agent_message` passes `cache_control=True` on every reactive call (`src/conexus/core/agent_handler.py:152`). Expected 30–60 % input-token savings on reactive turns.
- **Tool schema generator silently downgrades unknown Python types to `{"type":"string"}`** (`core/tools/schema_gen.py:38`). `Literal`, `Enum`, `Annotated`, nested Pydantic models, and `dict[str,Any]` all become free-form strings — a correctness bug flagged directly by [[03-tool-integration]] (strict JSON Schema / `additionalProperties:false`) and [[12-cost-token-optimization]] (structured outputs halve retry spend). **Resolved in PR1** ([fix/cluster-a-pr1-schema-gen-and-wal](https://github.com/leandrotcawork/conexus-framework/pull/2)).
- **Observability is a blind spot.** No `trace_id`, no OTel spans, no per-tool-call ledger, no cache-hit/cache-write columns in `UsageTracker`. [[09-observability-evaluation]] calls this out as table-stakes; today a post-mortem of "what did Ana do at 02:13?" requires reading raw `llm_usage` rows and correlating by timestamp.
- **No eval harness.** Zero promptfoo / DeepEval / snapshot regression. Every prompt change to `SKILL.md` is shipped blind. [[09-observability-evaluation]] and [[10-deployment-runtime §10]] explicitly mark this as the second CI lane you need.
- **Retrieval on the knowledge wiki is lexical-substring only** (`core/memory/wiki_store.py`, `search()` reads every file and does `in`-match). No BM25, no embeddings, no rerank. [[07-rag-retrieval]] is unambiguous: a naive substring index is worse than no search past ~50 documents because it teaches the agent the corpus is dumb.
- **Memory taxonomy is flat.** [[04-memory-systems]] defines working / short-term / episodic / semantic / procedural. Conexus has only short-term (`chat_history`, hard-capped at last 10, no rolling summary) and semantic (wiki). No MemGPT-style self-editable core block, no Mem0-style ADD/UPDATE/DELETE extractor, no conversation summarisation.
- **Scheduler job-store is in-memory only.** `core/scheduler/scheduler.py` does not configure `SQLAlchemyJobStore`; job definitions live in RAM and are re-registered at boot. Idempotency rides entirely on `ping_log`. [[10-deployment-runtime §5]] accepts this, but the `pending`/`sent` ambiguity (NULL `sent_at` means either "in-flight" or "failed") bites every time a crash occurs mid-job. **`ping_log` tri-state resolved in PR2** ([fix/cluster-a-pr2-cache-control-and-ping-log](https://github.com/leandrotcawork/conexus-framework/pull/3)): `attempts`, `failed_at`, `last_error` columns added; `ping_mark_pending` inserts with `attempts=1` and increments on conflict; `ping_mark_failed` sets `failed_at`/`last_error`; `ping_was_sent` returns `True` when `sent_at IS NOT NULL OR attempts >= 3`; idempotent migration with backfill (`src/conexus/core/memory/sqlite_store.py:216-228`).
- **No MCP.** [[11-mcp]] is the interoperability bet for 2026; Conexus tools are all hard-coded Python. Not a gap that hurts today (single operator, single process), but it's the natural way to expose Google Calendar / wiki to Claude Desktop, and it's a no-brainer add for the Pesquisador `web_fetch` path.
- **Top-5 fixes, ranked by (impact / effort):** (1) pull timestamp out of system prompt, add `cache_control` on system + tool schemas; (2) add `trace_id` column + propagation through `handle_agent_message` → `AgentRegistry` → `UsageTracker`; (3) stop silent-stringifying in `schema_gen._type_to_schema`; (4) wire a minimal promptfoo golden set into CI; (5) add BM25 + frontmatter-aware chunking to `WikiStore.search`.

---

## 2. Strengths (tied to code)

- **Unified tool-calling loop.** `core/agent_handler.py` is the *only* ReAct driver, exactly as [[01-agent-fundamentals]] recommends. No per-agent copies.
- **Declarative agents via `SKILL.md`.** `core/config/skill_loader.py:35-45` parses YAML frontmatter into a typed Pydantic model; adding an agent is YAML + one tools class ([[02-frameworks-survey]] "declarative skill" pattern).
- **Auto-generated OpenAI tool schemas.** `core/tools/schema_gen.py` walks `inspect.signature` + `typing.get_type_hints`, filtered by `tools:` allowlist ([[03-tool-integration]] "schemas from code, not hand-maintained JSON").
- **Central dispatch with uniform error shape.** `core/agent_registry.py:execute_tool` returns a JSON string for every outcome, exceptions wrapped as `{"error": ...}` — never raises into the loop ([[03-tool-integration]] idempotent tool contract).
- **Typed LLM budgets with notify/halt semantics.** `core/budget/cap_checker.py` + `BudgetCap` on SKILL.md (`on_exceed: notify|halt`); recent fix `d1ba537` made the semantics correct ([[12-cost-token-optimization]] cost controls).
- **Context-tagged cost logging.** `core/llm/context_tag.py` ContextVar + `UsageTracker.by_context()` lets `/uso` break cost down by `reactive` / `briefing` / `synthesis` ([[09-observability-evaluation]] attribution).
- **Retries + provider fallback.** Phase 2 (branch `refactor/llm-layer-litellm-primitives`, commit `6dee0fe`) landed `LLMService` (`src/conexus/core/llm/service.py`) wrapping `litellm.Router` with `num_retries=3`, `cooldown_time=60`, and SKILL.md-declared fallback chain — replacing the hand-rolled tenacity loop that lived in `core/llm/router.py:107-120`. `router.py` was deleted in Phase 4 (commit `f3c82b5`). See `docs/wiki/litellm/03-router.md` for `litellm.Router` API. ([[10-deployment-runtime §6]] back-pressure.)
- **Idempotent scheduled jobs via `ping_log`.** `agents/ana/jobs.py:31-48` and `agents/pesquisador/jobs.py:20-37` use mark-pending → body → mark-sent ([[10-deployment-runtime §5]]).
- **Git-backed knowledge wiki with path-escape guard.** `core/memory/wiki_store.py:22-28` validates against `..` traversal before writing; Pesquisador uses explicit `git_sync` tool rather than per-write autocommit ([[04-memory-systems]] / [[07-rag-retrieval]] persistent-memory pattern).
- **Single-machine SQLite on Fly volume.** Matches the [[10-deployment-runtime §8]] sweet-spot for a solo operator.
- **Two-model cascade on Pesquisador.** Cheap Flash for tool-calling, Gemini Pro only for `compile_article` — exactly the cost pattern in [[12-cost-token-optimization §3]].
- **Typed, idempotent tool method signatures across both agents.** Tools return dict/list/str; registry serialises. Matches [[03-tool-integration]] contract.
- **ToolBackend abstraction with backward-compatible registry (Phase 7).** `src/conexus/core/agent_registry.py` now routes through a `dict[str, ToolBackend]`. The original `register(agent, tools_obj)` API is preserved — it wraps the tools object in `PythonBackend` automatically. `register_backend(agent, backend)` admits any `ToolBackend` subclass. `McpStdioBackend` (`src/conexus/core/backends/mcp_stdio_backend.py`) provides subprocess JSON-RPC 2.0 MCP client dispatch on the same interface.
- **SKILL_PACK format + SkillLoader (Phase 7).** `src/conexus/core/skills/pack_loader.py` defines `SkillPackDocument` / `SkillPackFrontmatter` / `SkillPackBackend`. `src/conexus/core/skills/skill_resolver.py` resolves the `skills:` list from `SkillFrontmatter`, loads `SKILL_PACK.md`, registers backends into the registry, and returns merged `tool_tags` + prompt fragments. `skills: list[str]` field added to `SkillFrontmatter` in `src/conexus/core/config/skill_loader.py:46`.
- **TrifectaGuard — deterministic per-turn taint tracking (Phase 7).** `src/conexus/core/trifecta/guard.py` implements the lethal-trifecta defence: any turn that accumulates both `untrusted_read` and `private_read` taint will have `external_write` tool calls blocked. `DataClass` enum and `auto_tag()` heuristic live at `src/conexus/core/trifecta/tags.py`. Guard is opt-in via `tool_tags` field on `AgentHandlerConfig` (`src/conexus/core/agent_handler.py:39`); `None` disables it, preserving all existing behaviour. `conexus tag suggest <tools.py>` CLI (`src/conexus/cli/__main__.py:102`) auto-generates a starter `data_classes:` map.

---

## 3. Gap matrix

| # | Partition | Current state | Gap | Impact | Effort | Recommendation |
|---|---|---|---|---|---|---|
| 01 | [[01-agent-fundamentals]] | Single ReAct loop, max_turns fallback | No re-plan / summarise-and-continue on turn exhaustion; fallback_msg is dead-end | M | S | On turn-exhaust, summarise turn history into a user-role recap and run one more pass before giving up |
| 02 | [[02-frameworks-survey]] | Bespoke loop over LiteLLM | No graph/checkpoint primitives — crash mid-tool-call can re-run tool | M | L | Defer LangGraph; keep tools idempotent. Add `turn_checkpoint` table for post-mortem replay |
| 03 | [[03-tool-integration]] | **PR1:** `schema_gen` silent-string fallback fixed; `Literal`/`Enum`/`dict`/nested-Pydantic handled; raises on unknown types. Remaining: no `strict:true` / `additionalProperties:false`; no output schema; no SSRF guard in `web_fetch` | ~~Unknown types → silent `string`~~ — **resolved PR1**. No `strict:true` / `additionalProperties:false`; no SSRF guard in `web_fetch` | **M** (was H) | S-M | Add `strict`; parse docstrings for descriptions; allowlist scheme/host in `pesquisador.tools.web_fetch` |
| 04 | [[04-memory-systems]] | Chat_history (last 10), facts KV, wiki | No rolling summary past 10 msgs; no core-memory block; no Mem0-style extractor; no episodic log separate from chat | **H** | M | Add `conversation_summary` column; rolling compaction job; `memory_core` fact namespace injected verbatim in system prompt |
| 05 | [[05-context-engineering]] | **PR2:** timestamp removed from system prompt; `BuiltinTimeTools.get_current_time` on-demand tool; `_apply_cache_control` stamps `ephemeral` on system + last tool; `cache_control=True` in reactive loop (`src/conexus/core/agent_handler.py:152`, `src/conexus/core/llm/service.py:15`). Remaining: no XML/section delimiters; no progressive-disclosure for large tool outputs | ~~No `cache_control` markers; timestamp in system breaks stable prefix~~ — **resolved PR2**. No XML/section delimiters; no progressive-disclosure for large tool outputs | **M** (was H) | S | Wrap history/facts in `<chat_history>`/`<facts>` tags |
| 06 | [[06-multi-agent-orchestration]] | Two agents in one process, no cross-talk; **Phase 8:** `Handoff` + `TeamRegistry` + `HandoffRouter` + `BudgetCascader` + `handoff_audit` shipped | No supervisor execution loop yet; `trace_id` propagation still pending; no live fan-out between real agents | M | M | Keep two-agent shape; add `trace_id` contextvar; skip supervisor execution loop until there's a concrete use-case |
| 07 | [[07-rag-retrieval]] | `WikiStore.search` = `str.__contains__` over every file; no chunking, no ranking | No BM25, no hybrid, no rerank, no frontmatter-aware chunking, no embedding store | **H** | M | Phase A: BM25 over Markdown paragraphs with frontmatter metadata filter; Phase B: sqlite-vec + cross-encoder rerank if Phase A insufficient |
| 08 | [[08-planning-reasoning]] | Pure ReAct, temperature 0.4 Ana / 0.2 Pesq | No Plan-and-Execute / ReWOO / Reflexion; no explicit "plan first" scratchpad | L | S | Optional — add a "plan" system-prompt instruction for Pesquisador compile_article path only |
| 09 | [[09-observability-evaluation]] | `llm_usage` table, `/uso` command | No OTel/Langfuse, no per-tool span, no trace_id, no eval harness, no golden set, no drift monitoring | **H** | M | Add `trace_id` now; minimal promptfoo golden set in CI; defer full OTel export until a second operator shows up |
| 10 | [[10-deployment-runtime]] | **PR1:** `PRAGMA journal_mode=WAL; synchronous=NORMAL` enforced on connect (`src/conexus/core/memory/sqlite_store.py`). **PR2:** `ping_log` tri-state (`attempts`, `failed_at`, `last_error`) shipped (`src/conexus/core/memory/sqlite_store.py:431-480`). Remaining: APScheduler jobs not in `SQLAlchemyJobStore`; no `misfire_grace_time` / `coalesce` per job; no `/healthz` | ~~No WAL pragma~~ — **resolved PR1**. ~~Ambiguous `ping_log` pending state~~ — **resolved PR2**. APScheduler in-memory; no misfire grace; no `/healthz` | M | S | Add misfire grace + coalesce; `/healthz` HTTP endpoint |
| 11 | [[11-mcp]] | MCP-stdio **consume** path shipped (Phase 7). `McpStdioBackend` + `SkillLoader` + `SKILL_PACK.md` let any agent consume stdio MCP servers (`src/conexus/core/backends/mcp_stdio_backend.py`, `src/conexus/core/skills/skill_resolver.py`). No MCP *expose* (producer) yet — cannot reach tools from Claude Desktop. | `tools/list` auto-registration deferred; `mcp-http` backend defined but not implemented; no FastMCP producer wrapper yet | L-M | M-remaining | Write a thin FastMCP producer wrapper over `AgentRegistry` for Claude Desktop access; wire `mcp-http` backend; auto-populate `tools_schema` from `tools/list` response |
| 12 | [[12-cost-token-optimization]] | Per-call usage logged, two-tier routing (Pesq), budget cap | No prompt caching; timestamp-in-system cache-bust; no cache_read/write tokens; no tool-output truncation by pagination (only hard-cut sentinel); no Batch API for non-urgent briefings; `compile_article` `max_tokens=16000` unbudgeted | **H** | S-M | `cache_control` on system + tools; cache-metric columns; structured pagination for tool outputs; cap `compile_article` at 8k + length-aware truncation upstream |

Impact: **H** = directly affects correctness, cost, or user-visible behaviour in a way Leandro will feel within a week. **M** = affects maintainability or edge-case correctness. **L** = nice-to-have.

---

## 4. Deep dives

### 4.1 [[01-agent-fundamentals]] — Agent loop, termination, determinism

The wiki frames an agent as *model + tools + loop + memory*, with termination on (a) final text, (b) max turns, (c) budget exceeded, (d) explicit halt tool. Conexus implements (a) and (b) in `core/agent_handler.py:85-150` and (c) implicitly via `CapChecker` *before* the loop — not during — so a runaway mid-loop can still blow the cap within a single request. The `max_turns` fallback at line 157 writes `cfg.fallback_msg` verbatim and gives up; no attempt to summarise or retry with a tighter prompt. Concrete fix: when `turn == max_turns and not assistant_text`, inject a synthetic user message ("sumarize o que você aprendeu nas últimas N ferramentas e responda ao usuário em uma frase") and run one more turn with `tool_choice="none"`. Also add a mid-loop budget check so a 12-tool turn cannot overshoot.

### 4.2 [[02-frameworks-survey]] — Framework choice

The wiki surveys LangGraph / LlamaIndex / OpenAI Agents SDK / Pydantic AI / Letta / custom-thin. Conexus is custom-thin over LiteLLM, which [[02]] endorses for a solo operator — the matrix explicitly calls out that LangGraph / Temporal overhead only pays off at "second operator" or "durable workflow required" thresholds. The one missing piece is the checkpointing contract: if `AgentRegistry.execute_tool` side-effects (Google Calendar create, wiki write-and-push) and then the process dies before the assistant turn is appended, on restart there is no log of "which tool calls already happened in this turn". Fix is a `turn_events` table written *inside* the loop at each tool boundary; at ~20 lines of code it's cheap insurance and survives the ride to a future LangGraph swap.

### 4.3 [[03-tool-integration]] — Tool schemas and execution

[[03]] is explicit: "if your schema generator falls back to `string` for unknown types, you have a silent correctness bug — the LLM will happily pass malformed JSON that parses but semantically loses information". `core/tools/schema_gen.py:38` is exactly that — any type not in its hardcoded map becomes `string`. `Literal["low","med","high"]` becomes free text; `PesquisadorTools.web_search(tier: int = 1)` becomes loosely-typed; `dict[str, Any]` params serialise arbitrary content as a single string. Three concrete fixes, all in `schema_gen.py`:
  1. Add `Literal` → `{"type":"string","enum":[...]}` and `Enum` → same.
  2. Add `dict[str, X]` → `{"type":"object","additionalProperties":<X>}`.
  3. Raise on truly-unknown types instead of falling back — fail loud at startup, not at runtime.
Also add OpenAI `strict: true` + `additionalProperties: false` at the schema root per [[03]] best practice, and wire docstring parsing so `_tool_schemas` becomes optional. Separately, `agents/pesquisador/tools.py:web_fetch` uses `httpx.get` with `follow_redirects=True` and no host/scheme allowlist — [[03]] calls out SSRF as the second most common tool-layer CVE. Add a `parse + validate` step that rejects `file://`, `localhost`, `169.254.*`, `10.*`, `192.168.*`, `fd00::/8`.

### 4.4 [[04-memory-systems]] — Working / short / episodic / semantic / procedural

[[04]] breaks memory into five layers. Conexus covers two: short-term (`chat_history`, hard-capped at `limit=10` in `core/agent_handler.py:58`) and semantic (wiki). There's no working memory beyond the per-turn message list, no episodic memory of "things that happened" distinct from "messages exchanged", and the facts KV is used as both semantic and core-memory without separation. Past ten messages, conversation context evaporates — a user who mentioned a deadline twelve messages ago gets no recall. Fix has three tiers: (a) add `conversation_summary` column to `chat_history` or a sibling table; run a rolling compaction every N messages where a cheap Flash call produces a 300-token summary that gets injected before the last 10 raw messages ([[04]] MemGPT pattern); (b) namespace facts into `core:` / `semantic:` — core gets injected verbatim into system prompt, semantic stays in the wiki; (c) if Pesquisador moves to per-topic research threads, add an episodic log of (topic, timestamp, outcome) separate from chat. Mem0-style ADD/UPDATE/DELETE extractor is further out but fits naturally as a cron job over recent `chat_history` rows.

### 4.5 [[05-context-engineering]] — Prompt structure, caching, delimiters

**PR2 resolved the cache_control + timestamp gap.** `handle_agent_message` (`src/conexus/core/agent_handler.py`) no longer appends the BRT timestamp to the system message. The timestamp is now available on demand via `BuiltinTimeTools.get_current_time` (`src/conexus/core/tools/builtin_time.py`). `LLMService._apply_cache_control` (`src/conexus/core/llm/service.py:15-43`) stamps `{"cache_control": {"type": "ephemeral"}}` on the system message's last content block and the last tool schema entry; the reactive loop passes `cache_control=True` (`src/conexus/core/agent_handler.py:152`).

Note: the team runner path (`run_team_message`, lines 324-329 in `agent_handler.py`) still appends `now_brt` to the system prompt — that path was not part of PR2 scope.

Remaining open items from the original analysis:
  1. `facts` and `chat_history` are still concatenated as one bare string. Wrapping in `<facts>…</facts>` and `<chat_history>…</chat_history>` per [[05]] delimiter guidance would be a free cache extension.
  2. `agents/ana/SKILL.md` system prompt + `main.py:225-268` appended "REGRA CRÍTICA" / "PROTOCOLO OBRIGATÓRIO DE PESQUISA" should be de-duplicated.
  3. `main.py:263` has a UTF-8 encoding bug (`â€"` where an em-dash should be).

### 4.6 [[06-multi-agent-orchestration]] — Topologies and handoffs

[[06]] lists supervisor / swarm / pipeline / hand-off-as-tool patterns. Conexus runs two agents in one process with zero cross-talk; that is a valid "isolated peers" topology from [[06 §2]] and it should stay that way until there's a concrete use-case for handoffs. The one thing to borrow *now* is `trace_id` propagation: a ContextVar set in `handle_agent_message` at turn 0, passed into `AgentRegistry.execute_tool` and persisted in every `llm_usage` + `ping_log` + tool-audit row. Future handoffs (Ana → Pesquisador "go research X and report back") become one-column joins instead of timestamp archaeology. `core/llm/context_tag.py` is already a ContextVar — extend it with `trace_id` alongside `context`.

### 4.7 [[07-rag-retrieval]] — Chunking, ranking, rerank

[[07]] lays out the 2026 stack: markdown-aware chunking → BM25 + embeddings hybrid → RRF merge → cross-encoder rerank → sqlite-vec or LanceDB as the store. `core/memory/wiki_store.py:search` is the naive baseline: iterate every `.md`, read the file, test `query in content.lower()`. As the knowledge wiki grows past ~50 articles (`pesquisador` already has three directories: `domains`, `entities`, `concepts`), recall will stay OK but precision collapses — the agent can't distinguish "article mentions topic" from "article is about topic". Two-phase fix:
  - **Phase A (sync, 2 hours):** BM25 over article bodies, with frontmatter (`confidence`, `domain`, `last_updated`) exposed as metadata filters. Use `rank_bm25` pure-Python — no new infra. Split each article into intro-paragraph + section-paragraphs per [[07]] markdown-aware chunking.
  - **Phase B (1-2 days):** Add `sqlite-vec` embeddings via `gemini-embedding-001`; hybrid BM25 + cosine with RRF; cross-encoder rerank (`ms-marco-MiniLM-L-6-v2` or call Gemini for reranking) on top-20. Only justified if Phase A precision complaints surface.

### 4.8 [[08-planning-reasoning]] — ReAct, Plan-and-Execute, ReWOO, Reflexion

Pure ReAct at temperature 0.4 / 0.2 is fine for Ana's reactive flow. Pesquisador's `compile_article` path, however, fits Plan-and-Execute: "(1) draft a list of 3–5 subtopics to research, (2) for each, call web_search + web_fetch, (3) synthesise". Currently the agent decides these steps inline and the LLM-as-controller can skip step 2 if it thinks it already knows the topic — which it often does, and produces low-quality articles. Fix: add a system-prompt hint *only* during `compile_article` flow (check via `set_context`) to first output a plan JSON, then execute. Don't adopt ReWOO/Reflexion — they pay off at 10+ tool calls per task, which Conexus rarely hits.

### 4.9 [[09-observability-evaluation]] — OTel, Langfuse, evals

Zero observability beyond `llm_usage` rows. [[09]] wants: (1) OTel GenAI spans per LLM call and per tool call; (2) `trace_id` linking them; (3) Langfuse or a homebrew dashboard; (4) an eval harness — promptfoo / DeepEval / Ragas — running a golden set on every merge. Conexus has none of (1)-(4). Pragmatic ladder for a solo operator:
  - **Week 1:** Add `trace_id` column to `llm_usage` + `ping_log`. Log tool-call events to a new `tool_audit` table (`trace_id, agent, tool_name, args_json, result_json, duration_ms, error`). This alone answers 80 % of "what did Ana do?" questions.
  - **Week 2:** Minimal `promptfoo` config with 15–20 scenarios (morning briefing with 0 events, with 5 events; wiki-write with bad YAML; calendar create with ambiguous time; etc.). Run on every push; gate merges on "no regression in tool-call sequence".
  - **Deferred:** Full Langfuse / OTel until there's a second operator or an incident that needs replay.

### 4.10 [[10-deployment-runtime]] — Fly, APScheduler, SQLite

The Fly-single-machine + SQLite-on-volume shape is *exactly* the [[10 §8]] recommendation. What's missing is operational hygiene:
  - **WAL enforced — resolved PR1.** `src/conexus/core/memory/sqlite_store.py` now runs `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL` on connect. [[10 §3]] mandatory for concurrent-reader-under-async; done.
  - **APScheduler job store is in-memory.** `core/scheduler/scheduler.py` builds `AsyncIOScheduler()` with no `jobstores=` kwarg; jobs are re-registered every boot from `main.py`. That's fine because idempotency rides `ping_log`, but `misfire_grace_time` is default (1 s) and there is no `coalesce=True`. A Fly deploy that takes 90 s will *skip* the `pre_event */5` fire silently. Fix: per-job misfire grace (briefing: 30 min; recap: 60 min; pre_event: 60 s with coalesce true; todo_sweep: 30 min; lint: None).
  - **ping_log tri-state — resolved PR2.** `sent_at IS NULL` ambiguity is fixed. `src/conexus/core/memory/sqlite_store.py` now has `attempts`, `failed_at`, `last_error` columns. `ping_mark_pending` inserts with `attempts=1` and increments on conflict (`sqlite_store.py:431-436`). `ping_mark_failed` sets `failed_at`/`last_error` without touching `attempts` (`sqlite_store.py:450-454`). `ping_was_sent` returns `True` when `sent_at IS NOT NULL OR attempts >= 3` (dead-letter cap, `sqlite_store.py:473-480`). Idempotent migration with backfill for existing `sent_at IS NOT NULL` rows (`sqlite_store.py:216-228`).
  - **No `/healthz`.** [[10 §10]] calls it out for deploy health checks. Add a tiny aiohttp/FastAPI endpoint pinging LLM router + volume write + SQLite SELECT.
  - **Encoding bug.** `main.py:263` has `â€"` literal where em-dash should be — almost certainly a Windows/UTF-8 round-trip. Grep-fix the file with `rg --encoding utf-8 'â€'` and re-save.

### 4.11 [[11-mcp]] — Model Context Protocol

**Phase 7 partially closed this gap.** The MCP-stdio *consume* path now ships:

- `McpStdioBackend` (`src/conexus/core/backends/mcp_stdio_backend.py`) — subprocess JSON-RPC 2.0 MCP client with `start()` / `stop()` lifecycle.
- `SkillLoader` (`src/conexus/core/skills/skill_resolver.py`) — wires `SKILL_PACK.md` (backend: `mcp-stdio`) + `mcp.json` into `AgentRegistry` via `register_backend()`.
- `AgentRegistry.execute_tool()` now dispatches to `ToolBackend.execute()` regardless of whether the backend is in-process Python or a subprocess — the handler loop is unchanged.

What remains open:

1. **`tools/list` auto-registration.** `McpStdioBackend` dispatches tool calls by name but does not yet call `tools/list` on start to auto-populate `tools_schema`. That wiring must be done manually for each MCP server.
2. **MCP *producer* (Conexus as host).** Still unimplemented — no FastMCP wrapper over `AgentRegistry`. Claude Desktop cannot reach Conexus tools. [[11 §9b]] is still future work.
3. **`mcp-http` backend.** `SkillPackBackend.mcp_http` is defined in the enum (`src/conexus/core/skills/pack_loader.py:13`) but `SkillLoader` has no branch for it yet.

The remaining effort for (1) and (2) combined is roughly half a day as [[11 §8]] predicted — the backend abstraction is in place; only the schema-auto-population and producer wrapper are missing.

### 4.12 [[12-cost-token-optimization]] — Caching, routing, batching, truncation

Biggest wins in the repo sit here. Concrete list:
  - **Prompt caching absent.** `core/llm/service.py` (`LLMService`) does not yet pass `cache_control` blocks. With Gemini 2.5 Flash's implicit cache and Anthropic's explicit 4-breakpoint cache (if/when a Claude model is added), system prompt + tool schemas + stable facts are the obvious cache targets. Combined with the timestamp-fix from §4.5, expect 30–60 % input token savings on reactive turns.
  - **No cache_read/write tokens tracked.** `core/llm/usage_tracker.py:16` schema lacks `cache_read_tokens` / `cache_write_tokens` / `cache_cost_usd` columns. You can't measure the win from the above if you don't log it.
  - **`compile_article` unbudgeted 16k output.** `agents/pesquisador/tools.py:281` passes `max_tokens=16000` to Gemini Pro preview. A single article call at Pro pricing can approach the daily $0.15 Pesquisador cap on its own. Fix: drop to 6-8k, add a `length_hint` parameter controlled by article complexity, and move the prompt template to a file rather than inline string literal.
  - **Tool-output truncation is a hard cut.** `core/agent_handler.py:145-147` appends `"\n[... truncado]"` when over `result_max_chars`. [[12 §5]] wants paginated tool outputs with an opaque `cursor` param — the LLM can ask for more if needed instead of losing data silently. Add a `page_cursor` kwarg to large-output tools (`wiki_list`, `calendar_list_events`, `web_search`).
  - **Batch API not used.** Morning briefing and recap are non-urgent by wall-clock — they run once per day, user reads them minutes later. Anthropic/OpenAI Batch APIs give 50 % off with 24 h SLA; Gemini has similar. [[12 §4]] flags this as the one scheduled-work optimisation that pays for itself. Gate: only if daily spend crosses $X.
  - **No RTK-wrapped tool output normalisation.** User's own `rtk` CLI savings (60-90 %) apply to CI/dev output, not runtime. Not a gap, note for completeness.

---

## 5. Cross-cutting bugs and risks

> **Phase 7 (2026-04-29) status note.** The tool-backend abstraction, SKILL_PACK format, and TrifectaGuard all shipped. The lethal-trifecta exfil vector (untrusted_read + private_read → external_write in one turn) is now blocked when `tool_tags` is set on `AgentHandlerConfig`. Items below that have been resolved in Phase 7 are noted inline.

- ~~**Cache-busting from timestamp placement.**~~ **Resolved PR2** ([fix/cluster-a-pr2-cache-control-and-ping-log](https://github.com/leandrotcawork/conexus-framework/pull/3)). Timestamp removed from `handle_agent_message` system message; `BuiltinTimeTools.get_current_time` on-demand tool added; `_apply_cache_control` stamps `ephemeral` on system + last tool schema. See §4.5.
- **Budget cap vs. scheduled jobs.** `ARCHITECTURE.md §9` and `core/budget/cap_checker.py` intentionally skip caps for jobs — "briefings must ship". But `compile_article` called from `make_proactive_research_job` (`agents/pesquisador/jobs.py:196-202`) uses Gemini Pro synthesis with 16k output and zero cap. A single Wednesday run can blow a month's Pesquisador spend. Add a *per-job* cap separate from the reactive `BudgetCap`.
- **Wiki write idempotency.** `core/memory/wiki_store.py` does not dedupe content-identical writes. A retry of `wiki_write(path, same_content)` produces an empty commit (`git commit --allow-empty` effectively). Add a content-hash check: read current file, compare SHA256, skip commit if identical.
- **Tool return JSON contract leaks.** ~~`AgentRegistry.execute_tool` (`core/agent_registry.py`) serialises tool return values to JSON via `json.dumps` without `default=str`.~~ **Resolved Phase 7.** `AgentRegistry` now delegates to `PythonBackend.execute()` (`src/conexus/core/backends/python_backend.py:20`) which calls `json.dumps(result, ensure_ascii=False, default=str)`. The coercion-without-logging concern remains — consider adding a log call when `default=str` is invoked on a non-primitive type.
- **Missing `trace_id` propagation.** Everywhere. No correlation between `llm_usage` rows and the user request that triggered them, beyond timestamps. Described §4.6 / §4.9.
- **Missing eval harness.** §4.9. Every SKILL.md change is shipped untested beyond unit tests of the tools themselves.
- **Missing rerank on wiki retrieval.** §4.7. Recall-only search at scale becomes anti-signal.
- ~~**`ping_log` idempotency tri-state.**~~ **Resolved PR2** ([fix/cluster-a-pr2-cache-control-and-ping-log](https://github.com/leandrotcawork/conexus-framework/pull/3)). `attempts`, `failed_at`, `last_error` columns added; `ping_was_sent` dead-letters at `attempts >= 3`. See §4.10.
- **No cache-hit metric in `UsageTracker`.** §4.12. Cannot measure caching wins even after implementing them.
- **Pesquisador `web_fetch` SSRF.** §4.3. `httpx.get` with default config, follows redirects, no host allowlist. Trivial to exploit if any tool-injection leaks.
- **Chat history hard-cap at 10, no summary.** §4.4. Past-cutoff context is silently dropped.
- **`main.py:225-268` hard-coded system-prompt append.** Bolts on "REGRA CRÍTICA" and "PROTOCOLO OBRIGATÓRIO" strings per agent outside `SKILL.md`. Violates the [[02]] "agent is a config file" contract — protocol should live in SKILL.md body.
- **Encoding bug `main.py:263`.** UTF-8 round-trip produced `â€"` literal.
- **`schema_gen.py` silent fallback.** §4.3. Most impactful correctness bug in the repo.
- **Wiki `git_sync` blocks the agent loop.** `core/memory/wiki_store.py` pull-rebase-push is synchronous with a 30-second httpx-style timeout. If the git remote hangs, the Telegram reply stalls. Offload to `asyncio.to_thread` or an out-of-band commit queue.
- **Voice transcription bypasses router.** `core/messaging/telegram_bot.py:178` calls `litellm.acompletion` directly — bypasses `LLMService`, so transcription cost is unlogged. Violates `ARCHITECTURE.md §9` invariant ("Every LLM call goes through `LLMService`").

---

## 6. Prioritised punch list

Format: *title — why — files — effort (S/M/L) — type (BUG/IMPROVE)*.

1. ~~**Remove timestamp from system prompt; add `cache_control` breakpoints.**~~ **Resolved PR2** ([fix/cluster-a-pr2-cache-control-and-ping-log](https://github.com/leandrotcawork/conexus-framework/pull/3)). `src/conexus/core/tools/builtin_time.py` (new), `src/conexus/core/llm/service.py:15-43`, `src/conexus/core/agent_handler.py:139-152`. **S**. IMPROVE.
2. ~~**Fix `schema_gen` silent string fallback.**~~ **Resolved PR1** ([fix/cluster-a-pr1-schema-gen-and-wal](https://github.com/leandrotcawork/conexus-framework/pull/2)). `Literal`/`Enum`/`dict`/nested-Pydantic handled; raises on unknown types. `strict:true`+`additionalProperties:false` still pending. `core/tools/schema_gen.py`. **S**. **BUG**.
3. **Add `trace_id` ContextVar + column.** Propagate through handler → registry → usage_tracker → ping_log. `core/llm/context_tag.py`, `core/agent_handler.py`, `core/agent_registry.py`, `core/llm/usage_tracker.py`, `core/memory/sqlite_store.py`. **S-M**. IMPROVE.
4. **Log cache_read/write tokens + costs in `UsageTracker`.** Schema migration + passthrough from `LLMService`. `core/llm/usage_tracker.py`, `core/llm/service.py`, `core/llm/cost.py`. **S**. IMPROVE.
5. **SSRF-guard `pesquisador.tools.web_fetch`.** Scheme allowlist + host blocklist + no-redirect-to-private-ip. `agents/pesquisador/tools.py`. **S**. **BUG**.
6. ~~**Fix `ping_log` pending/failed ambiguity.**~~ **Resolved PR2** ([fix/cluster-a-pr2-cache-control-and-ping-log](https://github.com/leandrotcawork/conexus-framework/pull/3)). `attempts`, `failed_at`, `last_error` added; `ping_was_sent` dead-letters at `attempts >= 3`. `src/conexus/core/memory/sqlite_store.py:431-480`. **S**. **BUG**.
7. ~~**Enforce `PRAGMA journal_mode=WAL; synchronous=NORMAL`.**~~ **Resolved PR1** ([fix/cluster-a-pr1-schema-gen-and-wal](https://github.com/leandrotcawork/conexus-framework/pull/2)). At `SqliteStore.__init__`. `src/conexus/core/memory/sqlite_store.py`. **S**. **BUG**.
8. **Route voice transcription through `LLMService`.** Invariant violation — cost currently unlogged. `core/messaging/telegram_bot.py:178`. **S**. **BUG**.
9. **Cap `compile_article` output; move prompt to template file.** `agents/pesquisador/tools.py:281`. **S**. **BUG**.
10. **Add `tool_audit` table and register per-tool span.** `core/agent_registry.py`, `core/memory/sqlite_store.py`. **M**. IMPROVE.
11. **Add rolling conversation summary.** New `conversation_summary` column; compaction every N messages; inject into system build. `core/memory/sqlite_store.py`, `core/agent_handler.py`. **M**. IMPROVE.
12. **Dedupe wiki writes by content hash.** Skip commit if SHA256 identical. `core/memory/wiki_store.py`. **S**. **BUG**.
13. **Offload `git_sync` push to `asyncio.to_thread`.** Don't block reply. `core/memory/wiki_store.py`, `agents/pesquisador/tools.py`. **S**. **BUG**.
14. **Set per-job `misfire_grace_time` + `coalesce=True`.** `core/scheduler/scheduler.py`, `main.py` scheduler registration. **S**. **BUG**.
15. **Add `/healthz` endpoint.** Tiny aiohttp server on a side port; ping LLM + SQLite. `main.py`, new `core/health.py`. **S**. IMPROVE.
16. **Promptfoo golden set + GitHub Action gate.** 15-20 scenarios; run on push. New `evals/` dir. **M**. IMPROVE.
17. **BM25-based wiki search with frontmatter metadata filter.** Replace substring search. `core/memory/wiki_store.py`, add `rank_bm25` dep. **M**. IMPROVE.
18. **Move hard-coded system-prompt appendages from `main.py:225-268` into `SKILL.md` body.** And fix UTF-8 bug at :263. `main.py`, `agents/*/SKILL.md`. **S**. **BUG**.
19. **Mid-loop budget check.** Prevent 12-tool turn from overshooting cap. `core/agent_handler.py`, `core/budget/cap_checker.py`. **S**. IMPROVE.
20. **Parse tool docstrings for descriptions.** Remove need for `_tool_schemas` ClassVar. `core/tools/schema_gen.py`. **S**. IMPROVE.

### Phase 7 additions (2026-04-29, completed)

The following items were delivered in Phase 7 (v2 spec §1.3, §1.4, §1.8) and are not in the original punch list:

- **ToolBackend abstraction.** `src/conexus/core/backends/{base,python_backend,mcp_stdio_backend}.py`. `AgentRegistry` routes through `ToolBackend.execute()`; `register(agent, tools_obj)` backward-compat preserved. Fixes the `json.dumps` without `default=str` bug as a side-effect (`PythonBackend.execute():20` uses `default=str`). **Done.**
- **SKILL_PACK format + SkillLoader.** `src/conexus/core/skills/{pack_loader,skill_resolver}.py`; `skills:` field on `SkillFrontmatter`. Pip-installable skill packages with `python` or `mcp-stdio` backends. `SkillLoader._load_module` tightened to require `v.__module__ == mod.__name__` so imported third-party classes are not mistakenly picked up as tools. **Done.**
- **TrifectaGuard.** `src/conexus/core/trifecta/{tags,guard}.py`; `tool_tags` field on `AgentHandlerConfig`; guard hook in tool-call loop (`src/conexus/core/agent_handler.py:141-151`). Deterministic lethal-trifecta exfil prevention. Opt-in; off when `tool_tags is None`. **Done.**
- **`conexus tag suggest` CLI command.** `src/conexus/cli/__main__.py:114`. Prints `auto_tag()` heuristic results for every public method in a tools.py file. **Done.**
- **102 new tests.** `src/conexus/tests/test_framework_{pack_loader,trifecta,backends,trifecta_integration}.py`. All pass; ruff clean on `src/conexus/`. **Done.**

### Phase 8 additions (2026-04-30, completed)

The following items were delivered in Phase 8 (v2 spec team layer, commits d476101–6235bc8):

- **`Handoff` model.** `src/conexus/core/team/handoff.py`. Frozen Pydantic model with `schema_version`, `from_agent`, `to_agent`, `payload`, `context_mode`, `return_on`, `hop_count`, `max_hops`, `tags`, `trust_boundary_cleared`. `next_hop()` enforces `max_hops` hard limit. **Done.**
- **`TEAM_PACK.md` format + `parse_team_pack()`.** `src/conexus/core/team/team_pack.py`. `TeamPackFrontmatter` / `TeamBudget` / `TeamPolicy` Pydantic models; parser splits `---` frontmatter. **Done.**
- **`TeamLoader`.** `src/conexus/core/team/team_loader.py`. Validates members against available agents, manager in members, `budget.shares` sum to 1.0. **Done.**
- **`TeamRegistry`.** `src/conexus/core/team/team_registry.py`. Runtime view: `members`, `manager`, `policy`, `budget`, `edges_from()`. **Done.**
- **`HandoffRouter`.** `src/conexus/core/team/handoff_router.py`. Four-step resolution: explicit → `auto` edge → `when` edge → manager fallback → raise. `when` expressions are Python `eval` sandboxed against `{"__builtins__": {}}`. **Done.**
- **`BudgetCascader`.** `src/conexus/core/team/budget_cascader.py`. Per-member share enforcement against a shared pool; `notify` / `halt_member` / `borrow_from_pool` policies; `ShareExceeded` on halted member. **Done.**
- **Handoff audit table.** `src/conexus/core/memory/handoff_audit.py`. `handoff_audit` SQLite table; `init_handoff_audit()` + `record_handoff()`. **Done.**
- **Multi-backend `list_tools()` contract.** `ToolBackend.list_tools()` now abstract (`src/conexus/core/backends/base.py:13`); `AgentRegistry.execute_tool()` routes via `list_tools()` with collision detection (`src/conexus/core/agent_registry.py:41`); `McpStdioBackend` populates `_tool_names` from `tools/list` response at `start()` time (`src/conexus/core/backends/mcp_stdio_backend.py:33`). **Done.**
- **Cross-agent TrifectaGuard: `seed_taint` + `from_handoff`.** `src/conexus/core/trifecta/guard.py:13,30`. Taint propagates across handoff boundary; `trust_boundary_cleared` bypasses the exfil rule for explicitly-audited cross-agent paths. **Done.**
- **`incoming_handoff` on `AgentHandlerConfig`.** `src/conexus/core/agent_handler.py:40`. Three-branch guard creation in `handle_agent_message` at line 61. **Done.**
- **`conexus run-team` CLI subcommand.** `src/conexus/cli/__main__.py:102`. Dry-run validator for TEAM_PACK. **Done.**
- **Reference team pack.** `agents/teams/product_team/TEAM_PACK.md`. 3-member `product_team` with manager `pm`. **Done.**
- **Tests.** `test_framework_team_{handoff,pack,registry,router,budget,trifecta,integration}.py` + `test_framework_cli.py`. All pass. **Done.**

Remaining open gaps from the original punch list that Phase 8 did **not** close: multi-backend routing adds `list_tools()` but the `tools/list` auto-registration gap from §4.11 is now closed for `McpStdioBackend` (it calls `tools/list` at `start()`). The supervisor execution loop (running agents sequentially through `handle_agent_message`) and `trace_id` propagation remain future work.

---

## 7. Out-of-scope / deliberately deferred

- **Postgres migration.** [[10 §11]] ladder: single-process SQLite is correct until (a) `database is locked` errors appear under sustained load, (b) a second operator wants their own instance, or (c) multiple Fly machines become necessary. None applies. Deferring until *any* of the three triggers.
- **LangGraph / Temporal / DBOS durable workflows.** [[02-frameworks-survey]] + [[10 §4]] agree these pay off when "debugging what the agent did three hours ago" becomes a weekly task. With two agents and one operator, `ping_log` + a `tool_audit` table (punch-list #10) provides 90 % of the forensic value at 5 % of the operational overhead. Revisit if a third agent is added or if crash-mid-tool-call becomes a recurring incident.
- **Real multi-agent orchestration (supervisor / swarm).** [[06-multi-agent-orchestration]] patterns exist for cross-agent delegation. The Phase 8 substrate (`Handoff`, `HandoffRouter`, `BudgetCascader`, `TeamRegistry`, `handoff_audit`) is now in place. What remains deferred is the execution loop that calls `handle_agent_message` for each hop — and wiring Ana + Pesquisador into a live `TEAM_PACK`. Until there is a concrete use-case that requires both agents to cooperate in a single trace, the supervisor loop stays future work.
- **Letta / stateful-agent-server model.** [[04-memory-systems]] + [[10 §4]]. Flips client/server so the server owns memory. Overkill for a single-user Telegram bot where the "client" is always the same process and state lives on one Fly volume. The pieces we'd copy (self-editing core block, archival memory) can land as SQLite tables without adopting Letta.
- **Full OTel / Langfuse self-hosted.** [[09-observability-evaluation]]. Requires either Docker-compose on a second Fly app or SaaS. Solo-operator threshold says "add when something breaks and you can't reconstruct it from logs"; `llm_usage` + the proposed `tool_audit` table + `trace_id` cover reconstruction. Defer.
- **Cross-encoder rerank + vector store.** [[07-rag-retrieval]] Phase B. Only justified if BM25 (punch-list #17) produces visible precision complaints.
- **Batch API for briefings.** [[12 §4]]. Gate on daily spend > $X — at current run-rate it's not worth the 24 h SLA tradeoff.
- **Streaming tool calls / token-by-token output.** Telegram is final-message-only; streaming buys nothing until a web UI is added.

---

*Last updated: 2026-05-10 (PR2 landed). Cite partitions as `[[NN-partition-name]]`. When a punch-list item lands, link its PR in the line above and strike through the title.*

**PR log:**
- **PR1** `fix/cluster-a-pr1-schema-gen-and-wal` ([#2](https://github.com/leandrotcawork/conexus-framework/pull/2)) — punch-list #2 (schema_gen), #7 (WAL pragma).
- **PR2** `fix/cluster-a-pr2-cache-control-and-ping-log` ([#3](https://github.com/leandrotcawork/conexus-framework/pull/3)) — punch-list #1 (cache_control + timestamp removal), #6 (ping_log tri-state).
