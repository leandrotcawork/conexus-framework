# Conexus — Agent Framework Architecture

This document describes the **extensible agent framework** introduced in the Phase 2 refactor. It is the contract every new agent plugs into. For operational/deployment docs see `SYSTEM.md`.

---

## 1. Core idea

An agent in Conexus is not code — it is **a `SKILL.md` + a `Tools` class + optional `jobs.py`**.

```
agents/<name>/
├── SKILL.md     declarative config (YAML) + persona (markdown body)
├── tools.py     Tools class — methods the LLM may call
└── jobs.py      job-builder functions, one per scheduled task
```

`main.py` reads the skill, builds the runtime pieces, and hands them to a single generic handler. There is no per-agent message loop. Adding an agent is configuration + tool methods, not plumbing.

---

## 2. The five framework pieces

| Component | File | Responsibility |
|-----------|------|----------------|
| **Skill loader** | `core/config/skill_loader.py` | Parse YAML frontmatter + markdown body of `SKILL.md` into a validated `SkillDocument` (Pydantic). |
| **Schema generator** | `core/tools/schema_gen.py` | Build OpenAI-style tool schemas from a `Tools` class using `inspect` + `get_type_hints`, filtered by the `tools:` list in `SKILL.md`. Supports per-tool overrides via a `_tool_schemas` class attribute. |
| **Agent registry** | `core/agent_registry.py` | Hold the live `Tools` instance for each registered agent. Provides `execute_tool(agent_name, tool_name, args) -> str` — JSON-serialising the result and catching exceptions as `{"error": ...}`. |
| **Agent handler** | `core/agent_handler.py` | The *only* tool-calling loop. Runs up to `max_turns` iterations of `TrackedLLM.acall` → execute tool calls → loop, until the model returns text. Hydrates every call with facts, chat history, and current BRT time. |
| **Handler config** | `AgentHandlerConfig` dataclass | Bundles per-agent behaviour: name, LLM, tool schemas, `execute_tool` callable, system prompt, max turns, budget cap, progress map, result truncation, fallback message. |

Everything else (Telegram bot, scheduler, LLM router, stores) is shared infrastructure — agents consume it, they don't extend it.

---

## 3. Declarative SKILL.md contract

Frontmatter (YAML) — validated by `SkillFrontmatter` in `skill_loader.py`:

```yaml
name: Ana                            # display name
role: ...                            # short role label
language: pt-BR                      # user-facing language
prefix: pesq                         # optional command prefix (for shared bots)
goal: ...                            # one-liner injected at top of system prompt
tools:                               # whitelist of Tools methods exposed to LLM
  - calendar_list_events
  - ...
llm:                                 # primary model
  provider: gemini
  model: gemini-2.5-flash
  temperature: 0.4
  fallback:
    - { provider: gemini, model: gemini-3-flash-preview }
llm_synthesis:                       # optional second model (e.g. expensive synthesis)
  provider: gemini
  model: gemini-3.1-pro-preview
  temperature: 0.2
schedules:                           # proactive jobs; kind matches make_*_job in jobs.py
  - { kind: briefing, cron: "0 7 * * *" }
budget:                              # optional per-agent spend cap
  daily_usd: 0.25
  monthly_usd: 6.00
  on_exceed: notify
```

Body (markdown) — the persona + protocol text. `main.py` concatenates `goal + body + any hard-coded protocol instructions` to build the system prompt.

**Changing an agent's tools, model, budget, or schedule is a YAML edit — no Python change.**

---

## 4. Request lifecycle (reactive)

```
Telegram → TelegramBot → per-agent handler closure → handle_agent_message(cfg, store, cap_checker, body, progress)
```

Inside `handle_agent_message`:

1. **Budget check** — if `cfg.cap` exceeded, return `cap_exceeded_msg` without touching the LLM.
2. **Context build** — pull last 10 chat messages, optionally all facts, append current BRT datetime.
3. **Persist user turn** — `store.chat_append` so history survives even if the loop bails.
4. **Loop up to `max_turns`** (`set_context("reactive")` tags every LLM call for cost attribution):
   - `TrackedLLM.acall(messages, tools, tool_choice="auto")` — router picks provider, records usage.
   - If response has `tool_calls`: for each, parse args, optionally emit a progress message (`progress_map`), dispatch via `cfg.execute_tool` (which calls into `AgentRegistry`), truncate to `result_max_chars` if set, append as a `tool` message, continue.
   - Otherwise: append assistant text to history and return it.
5. **Fallback** — if the loop exhausts turns without text, store and return `fallback_msg`.

`cfg.execute_tool` is a thin closure; the actual dispatch lives in `AgentRegistry.execute_tool` so tool execution is uniform (sync/async both handled, exceptions serialised).

---

## 5. Proactive lifecycle (scheduled jobs)

Each agent exposes a handful of `make_*_job(tools, llm, send)` factories in `jobs.py`. `main.py` maps `SKILL.md` schedules to `JobSpec(agent, kind, cron, fn)` and registers them with `ConexusScheduler` (APScheduler).

- Jobs run outside the reactive loop → **budget caps don't block them** (deliberate: briefings must ship).
- Jobs use `ping_log` (SQLite) as a write-ahead log for idempotency: `ping_mark_pending` → do work → `ping_mark_sent`. A crash mid-send re-sends on next boot.
- `scheduler.catchup()` on startup fires missed `briefing`/`recap` if we're within the cutoff window.
- `set_context("proactive")` (or job-specific) tags LLM calls so `UsageTracker.by_context` can separate reactive vs. scheduled spend.

---

## 6. LLM stack

```
TrackedLLM (core/llm/router.py)
  ├─ LiteLLM completion()              — multi-provider abstraction
  ├─ UsageTracker.log_call()           — tokens, USD, context tag, timestamp → SQLite
  ├─ fallback chain (from SKILL.md)    — on rate limit / 5xx, try next provider
  └─ returns (response, actual_model_used)
```

Cost attribution: `context_tag.set_context(...)` is a contextvar set by the handler ("reactive") or the job ("proactive", "briefing", "recap", "synthesis", etc.). `UsageTracker.by_context()` aggregates for the `/usage` command.

Pricing tables live in `core/llm/pricing.py` — add new models there when routing them.

---

## 7. Storage surfaces

| Store | Backing | Purpose |
|-------|---------|---------|
| `SqliteStore` | `/data/conexus.db` | facts, todos, chat_history, ping_log, llm_usage |
| `WikiStore` (Ana) | `/data/wiki/*.md` | agent-local memory, autocommit on |
| `WikiStore` (Pesquisador) | `/data/knowledge/*.md` | git-backed knowledge base; commits handled by `git_sync` tool |
| `GoogleCalendarClient` | Google API | Ana's calendar CRUD (OAuth refresh token in env) |

All three are injected into the agent's `Tools` instance at startup — tools never reach into `main.py` or global state.

---

## 8. Adding an agent — checklist

1. **Scaffold**: `agents/<name>/{SKILL.md,tools.py,jobs.py,__init__.py}`.
2. **SKILL.md**: fill frontmatter (`llm`, `tools:`, `schedules`, `budget`). Write the persona body.
3. **tools.py**: define a `Tools` class. Every method the LLM calls must:
   - Have typed parameters (→ auto schema).
   - Return a JSON-serialisable value (dict/list/str).
   - Use injected stores (don't import globals).
   - Optionally define `_tool_schemas = {"tool_name": {"description": "...", "params": {...}}}` for per-param overrides.
4. **jobs.py**: one `make_<kind>_job(...)` per schedule kind. Must be idempotent via `ping_log`.
5. **main.py wiring** (copy Ana/Pesquisador block):
   - `parse_skill_file(...)` → build `LLMConfig` → `build_llm(...)`.
   - Instantiate `Tools`.
   - Build `BudgetCap` from frontmatter.
   - `generate_tool_schemas(ToolsClass, skill.frontmatter.tools)`.
   - `registry.register("<name>", tools)`; define `_execute(name, args)` closure over `registry.execute_tool("<name>", ...)`.
   - Build `AgentHandlerConfig` with name, llm, schemas, execute_tool, system prompt, limits.
   - Spawn a `TelegramBot` with the agent's token and a `handle_agent_message(cfg, ...)` closure.
   - Register scheduler jobs.
6. **Env vars**: add `TELEGRAM_<name>_BOT_TOKEN` (and any provider keys) to `.env.example` and Fly secrets.
7. **Tests**: tools (`tests/test_<name>_tools.py`), jobs (`tests/test_jobs.py` or a new file), and at minimum one handler test using a fake LLM.

No changes to `core/` should be needed for a normal new agent. If they are, the framework is leaking — extend the config dataclass, not the handler logic.

---

## 9. Invariants (don't break these)

- `handle_agent_message` is the **only** tool loop. Don't add a parallel one.
- `AgentRegistry.execute_tool` **always** returns a JSON string — success or `{"error": ...}` — never raises.
- Every LLM call goes through `TrackedLLM` (never `litellm.completion` directly) so usage is logged.
- Reactive calls check the cap **before** calling the LLM; jobs do not.
- `chat_append(user)` happens **before** the LLM loop so history is preserved on crash/timeout.
- Tool results are truncated via `result_max_chars` on the handler config, not inside tools (keep tools pure).
- Timezone in user-facing strings is always BRT (`America/Sao_Paulo`).
- Secrets never hit the wiki, the chat history, or commit logs — enforced by agent persona prompts *and* by never storing raw env into SQLite.

---

## 10. Where to look

| Question | File |
|----------|------|
| How is a user message handled end-to-end? | `core/agent_handler.py` |
| How are tools discovered and dispatched? | `core/agent_registry.py`, `core/tools/schema_gen.py` |
| How is SKILL.md parsed? | `core/config/skill_loader.py` |
| How does `main.py` wire an agent? | `main.py` (Ana block lines ~116-134, Pesquisador ~136-165, wiring ~167-240) |
| How is cost tracked? | `core/llm/router.py`, `core/llm/usage_tracker.py`, `core/llm/context_tag.py` |
| How do scheduled jobs stay idempotent? | `core/scheduler/scheduler.py` + `ping_log` methods in `core/memory/sqlite_store.py` |
| What tools exist per agent? | `agents/<name>/tools.py` + `tools:` list in `SKILL.md` |
