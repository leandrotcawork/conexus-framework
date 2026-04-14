# Conexus — Claude Code Context

Personal AI agent framework. Multiple agents (Ana, Pesquisador) share one core runtime and are orchestrated from `main.py`. Runs 24/7 on Fly.io (`gru`), talks over Telegram.

For the full system tour see `docs/SYSTEM.md`. For the agent framework see `docs/ARCHITECTURE.md`.

## Quick start

```bash
uv sync                         # install deps
uv run pytest                   # run the test suite
uv run python main.py           # run both bots + scheduler locally
```

Python 3.11+, managed with `uv`. Tests live in `tests/` and use `pytest-asyncio` (auto mode).

## Repository layout

```
main.py                     Entry point — wires bots, scheduler, agents
agents/<name>/              One folder per agent
    SKILL.md                Persona + YAML frontmatter (llm, tools, schedules, budget)
    tools.py                Tool methods the LLM can call (typed signatures)
    jobs.py                 Proactive scheduled job builders
core/
    agent_handler.py        Unified tool-calling loop — handle_agent_message()
    agent_registry.py       Central dispatch — AgentRegistry.execute_tool()
    config/skill_loader.py  Parses SKILL.md (YAML + body) into a Pydantic model
    tools/schema_gen.py     Builds OpenAI tool schemas from type hints + SKILL.md
    llm/                    LiteLLM router, usage tracker, pricing, context tags
    memory/                 SqliteStore, WikiStore, GoogleCalendarClient
    messaging/              TelegramBot wrapper
    scheduler/              APScheduler wrapper (ConexusScheduler + JobSpec)
    budget/                 CapChecker / BudgetCap
docs/specs/                 Design docs (read before changing a subsystem)
docs/plans/                 Implementation plans
tests/                      Mirror of core/ + agents/ + integration tests
```

## Architecture in one paragraph

Each agent is declared by a `SKILL.md` (YAML frontmatter + markdown persona). `main.py` loads the skill, builds a `TrackedLLM` from the `llm` block, auto-generates OpenAI tool schemas from `Tools` class type hints filtered by `tools:` list, wraps everything in an `AgentHandlerConfig`, and registers its `Tools` instance in the `AgentRegistry`. The single `handle_agent_message()` runs the tool-calling loop for any agent. Proactive work runs through `ConexusScheduler` with cron strings from `SKILL.md`. Budget is enforced per-agent via `BudgetCap` + `CapChecker` before each reactive call, and per-call cost is logged by `UsageTracker`.

## Commands

```bash
uv run pytest                           # full suite
uv run pytest tests/test_agent_handler.py -q  # one file
uv run pytest -k "router" -q            # by keyword
uv run python scripts/bootstrap_google.py    # one-time Google OAuth setup
uv run python scripts/seed_wiki.py            # seed Ana's wiki folder
```

Deployment (Fly.io):

```bash
fly deploy                              # from repo root; uses deployment/Dockerfile via fly.toml
fly logs                                # tail production logs
fly ssh console                         # shell into the running app
```

## Environment

Copy `.env.example` to `.env`. Required for local run: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_PESQ_BOT_TOKEN`, `AUTHORIZED_CHAT_ID`, `GEMINI_API_KEY`, Google OAuth trio (bootstrap via `scripts/bootstrap_google.py`). `CONEXUS_DATA_DIR` defaults to `./data` locally and `/data` on Fly.

## Adding a new agent

1. `mkdir agents/<name>/` with `SKILL.md`, `tools.py`, `jobs.py` (copy Ana or Pesquisador).
2. Declare `llm`, `tools:`, `schedules:`, `budget:` in `SKILL.md` frontmatter.
3. Define a `Tools` class — each method the LLM can call must have typed parameters; schemas are auto-generated.
4. Wire it in `main.py`: parse skill → build LLM → instantiate Tools → `registry.register(name, tools)` → build `AgentHandlerConfig` → create Telegram bot → add scheduler jobs.
5. Add a Telegram bot token env var and an agent-scoped handler closure.

See `docs/ARCHITECTURE.md` for the full framework contract.

## Conventions & gotchas

- **Language:** agent-facing prompts and user replies are pt-BR. Code, comments, and commits are English.
- **Timezone:** always `America/Sao_Paulo` (BRT). `handle_agent_message` appends current BRT time to every system prompt.
- **Tool results must be JSON strings.** `AgentRegistry.execute_tool` serialises them; tool methods return dict/list/str.
- **Don't bypass the registry.** New agent handlers should reuse `handle_agent_message`, not reimplement the tool loop.
- **Idempotency:** scheduled jobs write to `ping_log` before sending and mark after — survives restart. `scheduler.catchup()` runs once on boot.
- **Budget caps are advisory + enforced.** `on_exceed: notify` sends a Telegram message and blocks the reactive call. Jobs ignore the cap by design.
- **SQLite lives on the Fly volume** (`/data/conexus.db`). Wiki markdown lives alongside (`/data/wiki/`, `/data/knowledge/`).
- **Two separate Telegram bots** (Ana + Pesquisador) run in the same process; each has its own token and updater.
- **Pesquisador uses two LLMs:** cheap router (`llm:`) for tool-calling, Gemini Pro (`llm_synthesis:`) for `compile_article`. Keep both in `SKILL.md`.
- **Knowledge wiki is git-backed.** SSH deploy key is injected at startup (`main.py`); don't check it into the repo.
- **Never commit `.env`, `wiki_deploy`, or anything in `/data/`.** `.gitignore` already covers the standard cases.

## Testing notes

- `pytest-asyncio` is in `auto` mode — `async def test_*` functions are discovered automatically.
- `freezegun` is available for time-sensitive scheduler tests.
- `tests/conftest.py` sets up shared fixtures (temp SQLite, temp wiki dir, fake LLM).
- When adding a tool, add a test in `tests/test_<agent>_tools.py` and a schema-gen test if the signature is unusual.

## Design/plan docs

Before changing a subsystem, skim the matching spec:

- `docs/specs/2026-04-11-conexus-secretary-design.md` — Ana design
- `docs/specs/2026-04-12-pesquisador-design.md` — Pesquisador design
- `docs/plans/2026-04-12-*` — implementation plans (what's built, what's next)
- `docs/SYSTEM.md` — system-level operational docs (Fly.io, volumes, secrets)
- `docs/ARCHITECTURE.md` — agent framework contract (this is what to read for "how agents work")
