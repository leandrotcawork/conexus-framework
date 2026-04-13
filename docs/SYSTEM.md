# Conexus — System Documentation

> Personal AI agent infrastructure. Read this to understand how everything works,
> how to operate it, and how to add new agents.

---

## Table of Contents

1. [What Is Conexus?](#1-what-is-conexus)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Message Flow — Reactive (User Sends a Message)](#3-message-flow--reactive)
4. [Message Flow — Proactive (Scheduler Fires)](#4-message-flow--proactive)
5. [Agents: Ana](#5-agents-ana)
6. [Storage Layer](#6-storage-layer)
7. [LLM Stack](#7-llm-stack)
8. [Scheduler](#8-scheduler)
9. [Telegram Bot](#9-telegram-bot)
10. [Deployment: Fly.io](#10-deployment-flyio)
11. [Secrets & Environment Variables](#11-secrets--environment-variables)
12. [How to Add a New Agent](#12-how-to-add-a-new-agent)

---

## 1. What Is Conexus?

Conexus (also written Co-Nexus) is Leandro's personal AI agent infrastructure.
It runs 24/7 on Fly.io (São Paulo, `gru`) and communicates exclusively via Telegram.

**Currently running agents:**

| Agent | Role | Language |
|-------|------|----------|
| Ana   | Personal secretary / executive assistant | pt-BR |

**Planned agents:** Researcher (news/research), Code Manager (code analysis).

All agents share the same infrastructure:
- LLM routing via LiteLLM
- SQLite for memory, todos, chat history
- Markdown wiki on the Fly.io volume
- Telegram bot for all communication
- APScheduler for proactive tasks

---

## 2. High-Level Architecture

```mermaid
graph TB
    subgraph Fly.io ["Fly.io (gru — São Paulo)"]
        subgraph App ["conexus app · 512 MB · shared-cpu-1x"]
            MAIN["main.py\n(entry point / orchestrator)"]

            subgraph Core
                BOT["TelegramBot\n(python-telegram-bot)"]
                SCHED["ConexusScheduler\n(APScheduler)"]
                LLM["LLM Router\n(LiteLLM · TrackedLLM)"]
                TRACK["UsageTracker"]
                CAP["CapChecker / BudgetCap"]
            end

            subgraph Ana
                SKILL["SKILL.md\n(persona + config)"]
                TOOLS["AnaTools\n(14 tool methods)"]
                JOBS["jobs.py\n(5 scheduled jobs)"]
            end

            subgraph Storage
                DB["SQLite\n/data/conexus.db"]
                WIKI["Wiki\n/data/wiki/*.md"]
            end
        end

        VOL["/data volume\n(persistent)"]
    end

    TG["Telegram\n(cloud)"]
    GCAL["Google Calendar API"]
    GEMINI["Gemini API\n(gemini-2.5-flash)"]

    TG <-->|"HTTPS polling"| BOT
    BOT --> MAIN
    MAIN --> LLM
    LLM <-->|"HTTPS"| GEMINI
    TOOLS <-->|"OAuth2"| GCAL
    DB --- VOL
    WIKI --- VOL
```

---

## 3. Message Flow — Reactive

What happens when you send a message to Ana on Telegram.

```mermaid
sequenceDiagram
    participant L as Leandro (Telegram)
    participant BOT as TelegramBot
    participant MAIN as _handle_ana_message
    participant LLM as LiteLLM / Gemini
    participant TOOLS as AnaTools
    participant DB as SQLite
    participant GCAL as Google Calendar

    L->>BOT: Text or /voice message
    BOT->>BOT: Authorize (check chat_id)
    BOT->>MAIN: handler(body, prefix_agent)

    MAIN->>DB: chat_recent("ana", limit=10)
    MAIN->>DB: facts_list()
    MAIN->>MAIN: Build system prompt + messages[]

    loop Up to 6 turns
        MAIN->>LLM: completion(model, messages, tools=14, tool_choice="auto")
        LLM-->>MAIN: response

        MAIN->>DB: log_call (tokens, cost, context="reactive")

        alt LLM wants to call a tool
            MAIN->>TOOLS: _execute_tool(fn_name, args)
            TOOLS->>DB: read/write facts/todos
            TOOLS->>GCAL: calendar CRUD
            TOOLS-->>MAIN: JSON result
            MAIN->>MAIN: Append tool result to messages[]
        else LLM returns final text
            MAIN->>DB: chat_append(user)
            MAIN->>DB: chat_append(assistant)
            MAIN-->>BOT: reply text
        end
    end

    BOT-->>L: reply_text(reply)
```

**Key details:**
- Budget is checked before every reactive call. If daily limit ($0.25) is exceeded, Ana replies immediately without calling the LLM.
- Voice messages: Telegram OGG → base64 → Gemini multimodal → transcription text → same flow above.
- The system prompt includes the current date/time (BRT) and instructs Ana to use tools rather than describe what she would do.
- Chat history (last 10 messages) and all known facts are injected into every call.

---

## 4. Message Flow — Proactive

What happens when the scheduler fires a job.

```mermaid
sequenceDiagram
    participant SCHED as ConexusScheduler (APScheduler)
    participant JOB as Job fn (e.g. make_briefing_job)
    participant PING as ping_log (SQLite)
    participant TOOLS as AnaTools
    participant LLM as TrackedLLM
    participant BOT as TelegramBot.send_message

    SCHED->>JOB: run()
    JOB->>PING: ping_was_sent(kind, ref_id)?
    alt Already sent
        JOB-->>SCHED: return (idempotent)
    else Not sent yet
        JOB->>PING: ping_mark_pending(kind, ref_id)
        JOB->>TOOLS: calendar_list_events / todos_list / etc.
        JOB->>LLM: complete(prompt)   [briefing/recap only]
        LLM-->>JOB: text
        JOB->>BOT: send_message(text)
        JOB->>PING: ping_mark_sent(kind, ref_id)
    end
```

**Idempotency:** Every job uses `ping_log` as a write-ahead log. If the process crashes after sending but before marking as sent, it will re-send on restart. If it crashes before sending, it picks up at startup via `catchup()`.

**Catchup on startup:** `ConexusScheduler.catchup()` runs once at startup. For `briefing` and `recap`, if today's ping hasn't been sent yet (and we're before the cutoff hour), it fires immediately.

---

## 5. Agents: Ana

### Anatomy of an agent

Every agent consists of three files:

```
agents/<name>/
├── SKILL.md     ← persona, config (frontmatter) + system prompt (body)
├── tools.py     ← tool methods the LLM can call
└── jobs.py      ← proactive scheduled job builders
```

### Ana's SKILL.md (frontmatter)

```yaml
name: Ana
role: Assistente pessoal e secretária executiva
language: pt-BR
llm:
  provider: gemini
  model: gemini-2.5-flash
  temperature: 0.4
schedules:
  - { kind: briefing,   cron: "0 7 * * *"   }   # 07:00 daily
  - { kind: recap,      cron: "0 21 * * *"  }   # 21:00 daily
  - { kind: pre_event,  cron: "*/5 * * * *" }   # every 5 min
  - { kind: todo_sweep, cron: "0 9-20 * * *"}   # hourly 09-20
  - { kind: lint,       cron: "0 22 * * 0"  }   # Sunday 22:00
budget:
  daily_usd: 0.25
  monthly_usd: 6.00
  on_exceed: notify
```

### Ana's 14 tools

```mermaid
graph LR
    subgraph Calendar ["Google Calendar"]
        CE[calendar_create_event]
        CL[calendar_list_events]
        CU[calendar_update_event]
        CD[calendar_delete_event]
    end

    subgraph Memory ["SQLite: facts table"]
        MG[memory_get]
        MS[memory_set]
        ML[memory_list_facts]
    end

    subgraph Todos ["SQLite: todos table"]
        TA[todos_add]
        TL[todos_list]
        TD[todos_mark_done]
    end

    subgraph Wiki ["/data/wiki/*.md"]
        WR[wiki_read]
        WL[wiki_list]
        WS[wiki_search]
        WW[wiki_write]
    end
```

### Ana's 5 scheduled jobs

| Job | Cron | What it does |
|-----|------|--------------|
| `briefing` | `0 7 * * *` | Reads today's events + open todos → LLM → sends morning summary |
| `recap` | `0 21 * * *` | Reads today's events + open todos → LLM → sends evening recap |
| `pre_event` | `*/5 * * * *` | Queries next 10-20 min of events → sends `⏰ Em ~15 min: <title>` per event (no LLM) |
| `todo_sweep` | `0 9-20 * * *` | Checks for overdue todos → sends one consolidated warning per day (no LLM) |
| `lint` | `0 22 * * 0` | Weekly wiki audit — currently a stub that sends a confirmation |

---

## 6. Storage Layer

### SQLite database: `/data/conexus.db`

```mermaid
erDiagram
    facts {
        TEXT key PK
        TEXT value
        TEXT updated_at
    }

    todos {
        INTEGER id PK
        TEXT text
        TEXT due
        INTEGER done
        TEXT created_at
        TEXT done_at
    }

    chat_history {
        INTEGER id PK
        TEXT agent_name
        TEXT role
        TEXT content
        TEXT ts
    }

    ping_log {
        TEXT kind PK
        TEXT ref_id PK
        TEXT agent_name PK
        TEXT sent_at
    }

    llm_usage {
        INTEGER id PK
        TEXT ts
        TEXT agent_name
        TEXT provider
        TEXT model
        INTEGER input_tokens
        INTEGER output_tokens
        REAL cost_usd
        TEXT context
        INTEGER duration_ms
        TEXT error
    }

    failed_sends {
        INTEGER id PK
        TEXT kind
        TEXT payload
        TEXT error
        INTEGER attempts
        TEXT next_retry
    }
```

**Table purposes:**
- `facts` — Ana's persistent key-value memory. Set/get by name, e.g. `leandro_timezone = America/Sao_Paulo`.
- `todos` — Task list with optional due date. Status: `open` / `done`.
- `chat_history` — Last N messages per agent. Used to inject conversation context.
- `ping_log` — Idempotency guard for scheduled jobs. Prevents duplicate sends on restart.
- `llm_usage` — Every LLM call logged. Used by `/uso` command. Cost computed dynamically from token counts × pricing table.
- `failed_sends` — Outbox for failed Telegram sends (retry queue, v1 not yet implemented).

### Wiki: `/data/wiki/`

Flat filesystem of Markdown files, managed by `WikiStore`. Structure:

```
/data/wiki/
├── index.md           ← master index (links to all pages)
├── log.md             ← append-only change log
├── about/
│   └── conexus.md     ← what Conexus is
├── preferences/
│   └── leandro.md     ← Leandro's scheduling preferences, etc.
├── projects/          ← one file per project
├── people/            ← one file per person
└── procedures/        ← how-to guides Ana has learned
```

Ana reads `index.md` before every query, updates pages as she learns things, and appends to `log.md` after every change. WikiStore auto-commits to git on every write (fire-and-forget).

> **Local dev:** wiki lives at `data/wiki/` (gitignored). On Fly.io it's at `/data/wiki/` on the persistent volume. Seed with `fly ssh console -C 'python3 /app/scripts/seed_wiki.py'`.

---

## 7. LLM Stack

```mermaid
graph LR
    AGENT["Agent code\n(jobs / reactive handler)"]
    ROUTER["TrackedLLM\n(core/llm/router.py)"]
    LITELLM["LiteLLM\n(provider abstraction)"]
    GEMINI["Gemini API"]
    TRACK["UsageTracker\n→ SQLite llm_usage"]
    PRICE["pricing.py\n(USD/1M tokens table)"]

    AGENT -->|"complete(messages)"| ROUTER
    ROUTER -->|"litellm.completion()"| LITELLM
    LITELLM <-->|"HTTPS"| GEMINI
    ROUTER -->|"log_call(tokens)"| TRACK
    TRACK -->|"compute_cost()"| PRICE
```

**LLM flow:**
1. Agent calls `llm.complete(messages)` (proactive jobs) or `litellm.completion(tools=...)` directly (reactive handler).
2. `TrackedLLM` tries the primary provider (`gemini/gemini-2.5-flash`), falls back to secondary providers if configured.
3. On success: logs `(agent, provider, model, input_tokens, output_tokens, context, duration_ms)` to `llm_usage`.
4. On failure: logs the error and tries the next fallback.

**Current primary model:** `gemini/gemini-2.5-flash` — cheapest capable model with tool calling support.  
**Cost:** $0.15 / 1M input tokens, $0.60 / 1M output tokens.  
**Budget:** Ana is capped at $0.25/day, $6.00/month.

**Context tagging:** `core/llm/context_tag.py` uses a `ContextVar` so every LLM call is tagged with its context (`reactive`, `briefing`, `recap`, etc.) — visible in `/uso` breakdown.

**`/uso` command:** Shows cost by context for the last 30 days. Supports `today` / `week` args.

---

## 8. Scheduler

```mermaid
graph TB
    MAIN["main.py\namain()"]
    SCHED["ConexusScheduler\n(APScheduler AsyncIO)"]
    CATCHUP["catchup()\non startup"]
    JOBS["5 JobSpecs\n(ana:briefing, recap, pre_event,\ntodo_sweep, lint)"]
    APT["APScheduler\nCronTrigger × 5"]
    PING["ping_log\n(idempotency)"]

    MAIN -->|"add_job × 5"| SCHED
    MAIN -->|"scheduler.start()"| APT
    MAIN -->|"await catchup()"| CATCHUP
    CATCHUP -->|"check ping_log"| PING
    CATCHUP -->|"fire if missed"| JOBS
    APT -->|"cron fires"| JOBS
    JOBS -->|"check ping_log"| PING
```

**Catchup rules:**

| Job | Catchable? | Cutoff |
|-----|-----------|--------|
| briefing | Yes | 12:00 BRT |
| recap | Yes | end of day |
| pre_event | No | — (event-specific IDs) |
| todo_sweep | No | — |
| lint | Yes | none (weekly) |

---

## 9. Telegram Bot

```mermaid
graph TD
    TG["Telegram cloud"]
    POLLING["app.updater.start_polling()"]
    AUTH["_authorized(update)\ncheck chat_id == AUTHORIZED_CHAT_ID"]

    TG -->|"HTTPS long poll"| POLLING
    POLLING --> AUTH

    AUTH -->|"❌ wrong user"| DROP["silently drop"]

    AUTH -->|"✅ /uso or /usage"| USAGE["_on_usage()\n→ _handle_usage_cmd()"]
    AUTH -->|"✅ voice message"| VOICE["_on_voice()\n1. OGG → base64\n2. Gemini transcribe\n3. _split_prefix()\n4. message_handler()"]
    AUTH -->|"✅ text message"| TEXT["_on_message()\n1. _split_prefix()\n2. message_handler()"]

    TEXT --> HANDLER["_handle_ana_message(body, prefix)"]
    VOICE --> HANDLER
    USAGE --> USAGEFN["_handle_usage_cmd(args)"]
```

**Prefix routing:** `/ana hello` → handler("hello", "ana"). Currently only Ana is registered; the prefix is reserved for multi-agent routing when Researcher and Code Manager are added.

**Proactive sends:** `bot.send_message(text)` — called by scheduler jobs to push messages to Leandro without a triggering request.

**Authorization:** All messages from any chat_id other than `AUTHORIZED_CHAT_ID` are silently dropped. Single-user system.

---

## 10. Deployment: Fly.io

```mermaid
graph LR
    subgraph Local
        CODE["source code\n(git repo)"]
        DOCKERFILE["deployment/Dockerfile\n(uv + python:3.11-slim)"]
    end

    subgraph Fly_io ["Fly.io"]
        APP["conexus app\ngru (São Paulo)\nshared-cpu-1x · 512 MB"]
        VOL["/data volume\nconexus_data\n(persistent)"]
        SECRET["fly secrets\n(env vars)"]
    end

    subgraph External
        GCAL["Google Calendar API"]
        GEMINI["Gemini API"]
        TG["Telegram"]
    end

    CODE -->|"fly deploy"| APP
    DOCKERFILE -->|"image build"| APP
    VOL -->|"mounted at /data"| APP
    SECRET -->|"env injection"| APP
    APP <--> GCAL
    APP <--> GEMINI
    APP <--> TG
```

### Files involved in deployment

| File | Purpose |
|------|---------|
| `deployment/Dockerfile` | Image: `python:3.11-slim` + `uv` for deps |
| `fly.toml` | App config: region, memory, volume mount, TZ env |
| `pyproject.toml` / `uv.lock` | Python dependencies (reproducible via lock file) |
| `scripts/seed_wiki.py` | Run once after first deploy to create wiki structure |
| `scripts/bootstrap_calendar.py` | Run once locally to get Google OAuth tokens |

### Deploy sequence

```bash
# First-time setup
fly apps create conexus
fly volumes create conexus_data --region gru --size 1
fly secrets set TELEGRAM_BOT_TOKEN=... AUTHORIZED_CHAT_ID=... GEMINI_API_KEY=... \
    GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... GOOGLE_OAUTH_REFRESH_TOKEN=...

# Deploy (every time)
fly deploy

# Seed wiki (first time only, after deploy)
fly ssh console -C 'python3 /app/scripts/seed_wiki.py'

# View logs
fly logs

# SSH into machine
fly ssh console
```

### fly.toml key settings

```toml
app = "conexus"
primary_region = "gru"          # São Paulo — close to Leandro
[env]
  TZ = "America/Sao_Paulo"
  CONEXUS_DATA_DIR = "/data"    # Tells main.py where to put db + wiki
[[mounts]]
  source = "conexus_data"
  destination = "/data"         # Persistent volume
[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"              # 256 MB was OOM; 512 MB works fine
```

---

## 11. Secrets & Environment Variables

All set via `fly secrets set` in production, or `.env` file locally (never committed).

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `AUTHORIZED_CHAT_ID` | Your Telegram chat ID (only user allowed) |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `GOOGLE_CLIENT_ID` | OAuth 2.0 client ID (Google Calendar) |
| `GOOGLE_CLIENT_SECRET` | OAuth 2.0 client secret |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | Long-lived refresh token (from bootstrap script) |
| `CONEXUS_DATA_DIR` | Path to data dir (default `/data`). Set to `./data` for local dev |
| `GEMINI_MODEL` | Optional override for voice transcription model (default `gemini/gemini-2.5-flash`) |

---

## 12. How to Add a New Agent

Adding a new agent (e.g. Researcher) requires five steps.

### Step 1: Create the agent directory

```
agents/researcher/
├── __init__.py
├── SKILL.md
├── tools.py
└── jobs.py
```

### Step 2: Write SKILL.md

```markdown
---
name: Researcher
role: News and research analyst
language: pt-BR
goal: >
  Monitorar notícias e fornecer pesquisas aprofundadas sobre tópicos de interesse do Leandro.
tools:
  - web_search
  - memory_get
  - memory_set
  - wiki_write
llm:
  provider: gemini
  model: gemini-2.5-flash
  temperature: 0.2
schedules:
  - { kind: news_digest, cron: "0 8 * * *" }
budget:
  daily_usd: 0.50
  monthly_usd: 12.00
  on_exceed: notify
---

# Researcher — Analista de Pesquisa

## Sobre você
[system prompt here]
```

### Step 3: Write tools.py

```python
from dataclasses import dataclass
from core.memory.sqlite_store import SqliteStore
from core.memory.wiki_store import WikiStore

@dataclass
class ResearcherTools:
    store: SqliteStore
    wiki: WikiStore
    # add other clients (e.g. search API client) here

    def web_search(self, query: str) -> list[dict]:
        # ... call search API
        pass

    def memory_get(self, key: str) -> str | None:
        return self.store.fact_get(key)

    def memory_set(self, key: str, value: str) -> dict:
        self.store.fact_set(key, value)
        return {"ok": True}

    def wiki_write(self, path: str, content: str) -> dict:
        self.wiki.write(path, content)
        return {"ok": True}
```

### Step 4: Write jobs.py

```python
from agents.researcher.tools import ResearcherTools
from core.llm.router import TrackedLLM
from typing import Awaitable, Callable

def make_news_digest_job(
    tools: ResearcherTools,
    llm: TrackedLLM,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    async def run() -> None:
        # query news, run LLM, send digest
        pass
    return run
```

### Step 5: Wire into main.py

In `amain()`, after the Ana block, add:

```python
from agents.researcher.tools import ResearcherTools
from agents.researcher.jobs import make_news_digest_job

# Load Researcher
researcher_skill = parse_skill_file("agents/researcher/SKILL.md")
researcher_llm_cfg = LLMConfig(
    provider=researcher_skill.frontmatter.llm.provider,
    model=researcher_skill.frontmatter.llm.model,
    temperature=researcher_skill.frontmatter.llm.temperature,
)
researcher_llm = build_llm(researcher_llm_cfg, tracker, agent_name="researcher")
researcher_tools = ResearcherTools(store=store, wiki=wiki)

# Add tool schema (OpenAI format, same pattern as _ANA_TOOLS_SCHEMA)
_RESEARCHER_TOOLS_SCHEMA = [...]

# Add to scheduler
scheduler.add_job(JobSpec(
    "researcher", "news_digest", "0 8 * * *",
    make_news_digest_job(researcher_tools, researcher_llm, send_to_leandro)
))

# Add to prefix routing in _split_prefix (telegram_bot.py)
# Update: if name in {"ana", "researcher", ...}
```

### Architecture checklist for a new agent

- [ ] `SKILL.md` with frontmatter (name, llm, schedules, budget) and system prompt
- [ ] `tools.py` with a `@dataclass` class bound to `SqliteStore`, `WikiStore`, and any external clients
- [ ] `jobs.py` with one `make_<kind>_job` builder per schedule — each returns an `async def run()` closure
- [ ] Tool schemas added to `_<AGENT>_TOOLS_SCHEMA` in `main.py`
- [ ] Agent wired into `amain()`: skill loaded, LLM built, tools instantiated, jobs registered
- [ ] Prefix added to `_split_prefix()` in `telegram_bot.py` for direct routing (`/researcher <query>`)
- [ ] Budget cap added if needed
- [ ] Add `costs` entry to `pricing.py` if using a new model

---

*Last updated: 2026-04-12. All diagrams auto-render in GitHub, VS Code (Markdown Preview Mermaid), or any Mermaid-compatible viewer.*
