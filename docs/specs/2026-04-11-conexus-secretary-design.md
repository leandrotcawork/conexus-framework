# Conexus: Secretary Agent (Ana) — Design Spec

| Field   | Value |
|---------|---|
| Date    | 2026-04-11 |
| Status  | Approved in brainstorm; awaiting user review of written spec |
| Author  | Leandro Theodoro (with Claude) |
| Project | **Conexus** (agent framework) |
| Codename of first agent | **Ana** |

## 1. Overview

Conexus is a small, personal agent framework written in Python. This spec defines the first agent to ship: **Ana**, a proactive personal secretary running 24/7 on Fly.io.

Ana communicates through a Telegram bot, manages Leandro's Google Calendar, remembers structured facts and todos in SQLite, keeps long-term knowledge in a Karpathy-style markdown wiki (synced to a private GitHub repo, editable in Obsidian), and pings Leandro proactively — morning briefings, evening recaps, pre-event reminders, overdue-todo sweeps, and a weekly wiki lint.

The architecture is deliberately shaped to host a small **team** of agents. Two more agents (**Researcher**, **Code Manager**) will join as siblings of Ana in the following weeks, reusing Conexus's shared infrastructure: LLM router, memory system, cost tracker, Telegram bot, and scheduler.

## 2. Context & Constraints

- **Build deadline**: one weekend. Minimize moving parts, defer everything non-essential.
- **Monthly budget**: R$30 total (hosting + LLM API + all external services).
- **Deployment**: Fly.io free tier, single VM, single Python process, São Paulo region (`gru`).
- **Default language**: Ana replies in Brazilian Portuguese (pt-BR). Configurable per-agent.
- **Single user**: Ana is Leandro's alone; the bot is authorized only for one Telegram chat_id.
- **Team vision**: After Ana, add Researcher (news/tech tracking) and Code Manager (codebase analysis, task planning) as additional agents in the same Conexus framework.

## 3. Goals and Non-Goals

### Goals (v1 — this weekend)

1. Ana replies reliably to Telegram messages in pt-BR.
2. Ana reads and writes Google Calendar events.
3. Ana sends scheduled proactive messages: morning briefing (07:00), evening recap (21:00), pre-event pings (15 min before each event), overdue-todo sweeps (hourly, 09:00–20:00).
4. Ana remembers structured facts and todos in SQLite.
5. Ana maintains a long-form wiki in markdown, synced to a private GitHub repo, editable in Obsidian.
6. Every LLM call is tracked with tokens, cost, and a context tag, per agent.
7. LLM provider is swappable per-agent by editing `SKILL.md` (no code change).
8. Conexus project structure supports dropping in Researcher and Code Manager later without refactoring the core.

### Non-Goals (deferred to v2+)

1. Multi-user support.
2. Horizontal scaling.
3. Full observability stack (Prometheus/Grafana).
4. End-to-end encryption of wiki content beyond git and Fly volume privacy.
5. MCP-based integrations. Ana uses a custom Python Google Calendar tool in v1; MCP adoption is evaluated for Researcher and Code Manager in v2.
6. A dedicated manager/router agent. v1 uses explicit prefixes (`/ana`, `/researcher`, `/code_manager`) — Ana alone needs no prefix.
7. Full automated wiki lint prompt. The cron is wired; the lint prompt is stubbed for v1.
8. CI/CD pipeline. Manual deploys in v1.

## 4. Architecture

Ana runs as part of a single Python process on one Fly.io machine. No separate worker, no queue, no database server.

```
┌───────────────────────────────────────────────────────────────────┐
│                Fly.io (gru region) — single VM                    │
│                                                                   │
│  ┌──────────────────────────────────────────────────┐             │
│  │  Python process (main.py)                        │             │
│  │                                                  │             │
│  │  ┌─────────────────────┐  ┌─────────────────┐    │             │
│  │  │ python-telegram-bot │  │  APScheduler    │    │             │
│  │  │  (polling)          │  │  (briefings,    │    │             │
│  │  │                     │  │   recaps, pings)│    │             │
│  │  └─────────┬───────────┘  └────────┬────────┘    │             │
│  │            │                       │             │             │
│  │            └──────────┬────────────┘             │             │
│  │                       ▼                          │             │
│  │  ┌────────────────────────────────────────┐      │             │
│  │  │  agent_loader → CrewAI Agent: Ana      │      │             │
│  │  │                                        │      │             │
│  │  │  Tools: 16 total                       │      │             │
│  │  │   - calendar_{list,create,update,del}  │      │             │
│  │  │   - memory_{get,set,list_facts}        │      │             │
│  │  │   - todos_{add,list,mark_done}         │      │             │
│  │  │   - wiki_{read,list,search,write,      │      │             │
│  │  │           append_log,update_index}     │      │             │
│  │  └────────────┬───────────────────────────┘      │             │
│  │               │                                  │             │
│  │               ▼                                  │             │
│  │  ┌────────────────────────────────────────┐      │             │
│  │  │  core/llm/router  (LiteLLM-based)      │      │             │
│  │  │   - picks provider from SKILL.md       │      │             │
│  │  │   - logs usage per agent/context       │      │             │
│  │  └────────────────────────────────────────┘      │             │
│  │                                                  │             │
│  │  ┌────────────────────────────────────────┐      │             │
│  │  │  /data/conexus.db  (SQLite)            │      │             │
│  │  │   facts / todos / chat_history /       │      │             │
│  │  │   ping_log / llm_usage / failed_sends  │      │             │
│  │  └────────────────────────────────────────┘      │             │
│  │                                                  │             │
│  │  ┌────────────────────────────────────────┐      │             │
│  │  │  /data/wiki/  (git checkout)           │      │             │
│  │  │   index.md, log.md, about/, ...        │      │             │
│  │  └────────────────────────────────────────┘      │             │
│  └──────────────────────────────────────────────────┘             │
└───────────────────────────────────────────────────────────────────┘
          │               │                │                │
          ▼               ▼                ▼                ▼
   ┌──────────────┐ ┌──────────────┐ ┌────────────┐ ┌───────────┐
   │   Telegram   │ │    Google    │ │  LLM API   │ │  GitHub   │
   │   Bot API    │ │   Calendar   │ │ (Gemini    │ │ (private  │
   │              │ │     API      │ │ 2.0 Flash) │ │ wiki repo)│
   └──────────────┘ └──────────────┘ └────────────┘ └───────────┘
```

### Directory structure

```
conexus/
├─ core/                          # shared infrastructure
│  ├─ llm/
│  │  ├─ router.py
│  │  ├─ pricing.py
│  │  └─ usage_tracker.py
│  ├─ memory/
│  │  ├─ sqlite_store.py
│  │  └─ wiki_store.py
│  ├─ messaging/
│  │  └─ telegram_bot.py
│  ├─ scheduler/
│  │  └─ scheduler.py
│  ├─ config/
│  │  └─ skill_loader.py
│  ├─ budget/
│  │  └─ cap_checker.py
│  └─ __init__.py
│
├─ agents/
│  └─ ana/                        # the first agent
│     ├─ SKILL.md                 # canonical agent definition + wiki schema
│     ├─ tools.py                 # tool implementations
│     ├─ jobs.py                  # scheduled job definitions
│     └─ wiki/                    # Ana's persistent long-form memory
│        ├─ index.md
│        ├─ log.md
│        ├─ about/
│        ├─ preferences/
│        ├─ projects/
│        ├─ people/
│        └─ procedures/
│
├─ deployment/
│  ├─ Dockerfile
│  ├─ fly.toml
│  └─ .env.example
│
├─ scripts/
│  └─ bootstrap_google.py         # one-time OAuth bootstrap
│
├─ tests/
│  ├─ test_pricing.py
│  ├─ test_usage_tracker.py
│  ├─ test_scheduler_catchup.py
│  ├─ test_skill_loader.py
│  ├─ test_tools_calendar.py
│  └─ test_tools_wiki.py
│
├─ main.py                        # process entry point
├─ pyproject.toml
└─ README.md
```

## 5. Agent Configuration — SKILL.md

Every agent is defined by a single `SKILL.md` file: YAML frontmatter for configuration + markdown body for behavior, persona, and guardrails. `core/config/skill_loader.py` reads this file on startup and instantiates a CrewAI Agent from it.

This is the same pattern Claude Code uses for its skills, adopted here per-agent.

### Frontmatter schema

```yaml
---
name: string                  # display name
role: string                  # one-line role
language: 'pt-BR' | 'en' | 'auto'
goal: string                  # multi-line goal, used as CrewAI goal
tools: string[]               # tool function names exposed from tools.py

llm:
  provider: 'anthropic' | 'openai' | 'gemini' | 'deepseek' | ...
  model: string               # provider-specific model id
  temperature: float
  fallback:                   # optional ordered list; router tries in order
    - { provider: ..., model: ... }

schedules:                    # proactive jobs
  - { kind: string, cron: string }

budget:
  daily_usd: float
  monthly_usd: float
  on_exceed: 'notify' | 'halt'
---
```

### Ana's SKILL.md (v1)

```markdown
---
name: Ana
role: Assistente pessoal e secretária executiva
language: pt-BR
goal: >
  Ajudar Leandro a manter sua agenda organizada, lembrá-lo do que é
  importante, e ser uma presença calma e confiável no dia a dia.
tools:
  - calendar_list_events
  - calendar_create_event
  - calendar_update_event
  - calendar_delete_event
  - memory_get
  - memory_set
  - memory_list_facts
  - todos_add
  - todos_list
  - todos_mark_done
  - wiki_read
  - wiki_list
  - wiki_search
  - wiki_write
  - wiki_append_log
  - wiki_update_index
llm:
  provider: gemini
  model: gemini-2.0-flash
  temperature: 0.4
  fallback:
    - { provider: openai, model: gpt-4o-mini }
    - { provider: anthropic, model: claude-haiku-4-5 }
schedules:
  - { kind: briefing,   cron: "0 7 * * *" }
  - { kind: recap,      cron: "0 21 * * *" }
  - { kind: pre_event,  cron: "*/5 * * * *" }
  - { kind: todo_sweep, cron: "0 9-20 * * *" }
  - { kind: lint,       cron: "0 22 * * 0" }
budget:
  daily_usd: 0.25
  monthly_usd: 6.00
  on_exceed: notify
---

# Ana — Secretária do Leandro

## Sobre você
Você é a Ana, secretária pessoal do Leandro. Você fala português brasileiro,
de forma calorosa mas direta. Você nunca inventa informações que não estejam
no calendário, nos fatos, ou na sua wiki.

## O que você faz
- Gerencia a agenda do Leandro no Google Calendar.
- Lembra ele do que importa (reuniões, prazos, pendências).
- Mantém notas sobre preferências e contexto dos projetos dele em sua wiki.
- Envia briefing matinal às 07:00 e recap noturno às 21:00.
- Avisa 15 minutos antes de cada reunião.

## O que você NÃO faz
- Você nunca apaga eventos ou todos sem confirmação explícita.
- Você não envia mensagens proativas fora das rotinas programadas.
- Você não compartilha informações pessoais do Leandro com terceiros.
- Você não escreve senhas, tokens, ou dados sensíveis na wiki.

## Sua Wiki — como usar
Você mantém uma wiki de arquivos markdown em `agents/ana/wiki/`. Essa wiki
é sua memória de longo prazo. O Leandro também pode editá-la por fora.

### Convenções
- SEMPRE leia `index.md` antes de responder qualquer pergunta que possa
  envolver contexto histórico.
- Quando aprender algo substantivo: identifique as páginas afetadas, leia,
  atualize, atualize `index.md`, e faça append em `log.md`.
- Formato do log: `## [YYYY-MM-DD HH:MM] <kind> | <title>` seguido de
  1-3 linhas descrevendo o que mudou.
- Pastas canônicas: `about/`, `preferences/`, `projects/`, `people/`,
  `procedures/`. Não crie pastas novas sem uma boa razão.
- NUNCA escreva informações sensíveis (senhas, tokens, números de cartão).

### Fluxos
- **Ingest**: nova info → lê index → identifica páginas → atualiza → index → log.
- **Query**: pergunta → lê index → search/read páginas → responde com citações.
- **Lint** (semanal, domingo 22:00): revisa contradições e órfãs → resumo
  no Telegram.
```

## 6. Tools

Ana has **16 tools** total, organized by domain. Each tool is a typed Python function in `agents/ana/tools.py`, registered with CrewAI on startup.

### 6.1 Calendar (Google Calendar API — direct Python integration)

| Tool | Parameters | Returns |
|---|---|---|
| `calendar_list_events` | `start_iso: str`, `end_iso: str` | `list[Event]` |
| `calendar_create_event` | `title: str`, `start_iso: str`, `end_iso: str`, `description: str = None` | `{id: str}` |
| `calendar_update_event` | `event_id: str`, `title: str = None`, `start_iso: str = None`, `end_iso: str = None`, `description: str = None` | `{id: str}` |
| `calendar_delete_event` | `event_id: str` | `{ok: bool}` |

**Implementation decision**: Use `google-api-python-client` directly. A Google Calendar MCP server alternative was evaluated and deferred to v2. Rationale: simpler deployment (no subprocess), smaller container image, no subprocess lifecycle management, direct integration with our cost-tracking `ContextVar`. Migration to an MCP server later is a ~1 hour refactor of `tools.py` with no changes to the agent, SKILL.md, or cost tracking.

### 6.2 Memory (SQLite — structured facts)

| Tool | Parameters | Returns |
|---|---|---|
| `memory_get` | `key: str` | `str \| None` |
| `memory_set` | `key: str`, `value: str` | `{ok: bool}` |
| `memory_list_facts` | — | `list[{key, value}]` |

### 6.3 Todos (SQLite)

| Tool | Parameters | Returns |
|---|---|---|
| `todos_add` | `text: str`, `due_iso: str = None` | `{id: int}` |
| `todos_list` | `status: 'open' \| 'done' \| 'all' = 'open'` | `list[Todo]` |
| `todos_mark_done` | `id: int` | `{ok: bool}` |

### 6.4 Wiki (filesystem — markdown, git-backed)

| Tool | Parameters | Returns |
|---|---|---|
| `wiki_read` | `path: str` | `str` |
| `wiki_list` | `folder: str = ""` | `list[str]` |
| `wiki_search` | `query: str` | `list[{path, snippet}]` (full-text grep, no embeddings) |
| `wiki_write` | `path: str`, `content: str` | `{ok: bool}` |
| `wiki_append_log` | `kind: str`, `title: str`, `body: str` | `{ok: bool}` |
| `wiki_update_index` | `path: str`, `summary: str` | `{ok: bool}` |

### 6.5 Deliberately NOT a tool: `send_telegram`

Replies are returned by the agent to the bot layer, which sends them. The scheduler also sends directly to the bot, not through the agent. This prevents an agent from spamming the user or refusing to reply — the messaging channel is controlled by the framework, not by the agent.

## 7. Memory Model

Three tiers, each serving a distinct purpose.

### Tier 1 — SQLite (structured, fast, partially auto-loaded)

```sql
-- Structured personal facts Ana remembers
CREATE TABLE facts (
  key          TEXT PRIMARY KEY,
  value        TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

-- Lightweight todo list
CREATE TABLE todos (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  text         TEXT NOT NULL,
  due          TEXT,            -- ISO 8601, nullable
  done         INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL,
  done_at      TEXT
);

-- Last N messages of conversation (per-agent)
CREATE TABLE chat_history (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_name   TEXT NOT NULL,
  role         TEXT NOT NULL,   -- 'user' | 'assistant'
  content      TEXT NOT NULL,
  ts           TEXT NOT NULL
);

-- Proactive idempotency log
CREATE TABLE ping_log (
  kind         TEXT NOT NULL,   -- 'briefing' | 'recap' | 'pre_event' | 'todo_sweep' | 'lint'
  ref_id       TEXT NOT NULL,   -- date | event_id | iso week, depending on kind
  agent_name   TEXT NOT NULL,
  sent_at      TEXT,            -- NULL = write-ahead, not yet successfully sent
  PRIMARY KEY (kind, ref_id, agent_name)
);

-- Per-call LLM usage tracking
CREATE TABLE llm_usage (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL,
  agent_name      TEXT NOT NULL,
  provider        TEXT NOT NULL,
  model           TEXT NOT NULL,
  input_tokens    INTEGER NOT NULL,
  output_tokens   INTEGER NOT NULL,
  cost_usd        REAL NOT NULL,
  context         TEXT NOT NULL,   -- 'reactive' | 'briefing' | 'recap' | ...
  duration_ms     INTEGER,
  error           TEXT
);
CREATE INDEX idx_llm_usage_agent_ts ON llm_usage(agent_name, ts);

-- Queue for Telegram sends that failed transiently
CREATE TABLE failed_sends (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  kind         TEXT NOT NULL,
  payload      TEXT NOT NULL,
  error        TEXT NOT NULL,
  attempts     INTEGER NOT NULL DEFAULT 0,
  next_retry   TEXT NOT NULL
);
```

### Tier 2 — Chat history

The last N turns (default N=10) of the current conversation, retrieved from `chat_history` and injected into the agent's context on every reactive request.

### Tier 3 — Wiki (Karpathy method)

Long-form markdown knowledge owned by the LLM, git-backed, hand-editable in Obsidian.

**Three layers** (after Karpathy's gist):

| Karpathy's layer | Ana's version |
|---|---|
| Raw sources (immutable) | Telegram chat history, Google Calendar events, Leandro's "teach her" messages |
| The wiki (LLM-owned markdown) | `agents/ana/wiki/` |
| The schema (config) | `agents/ana/SKILL.md` — schema section |

**Folder layout**:

```
agents/ana/wiki/
├─ index.md            # catalog: every page with 1-line summary + last-updated
├─ log.md              # append-only chronological audit trail
├─ about/
│  ├─ leandro.md
│  ├─ conexus.md
│  └─ values.md
├─ preferences/
│  ├─ schedule.md
│  └─ communication.md
├─ projects/
│  └─ conexus_agents.md
├─ people/
└─ procedures/
```

**Core rule**: the wiki is NOT auto-loaded into every prompt. Ana reads it on-demand via `wiki_read` / `wiki_search`, starting from `index.md`.

**Three workflows**:

1. **Ingest** — new info arrives → Ana reads `index.md` → identifies affected pages → reads, updates → updates `index.md` → appends `log.md`.
2. **Query** — user asks a question → Ana reads `index.md` → searches/reads relevant pages → answers with citations → optionally files Q&A back as a new page.
3. **Lint** (weekly, Sunday 22:00) — Ana loads the full wiki → finds contradictions, stale claims, orphans, TODO markers → writes a report to `log.md` and sends a summary on Telegram. The cron is wired in v1 but the lint prompt is stubbed.

**Log entry format** (machine-parseable):

```markdown
## [YYYY-MM-DD HH:MM] <kind> | <title>
1–3 lines describing the change.
```

**Git backing**: `/data/wiki/` is a git checkout of a private GitHub repo. After every `wiki_write`, `wiki_append_log`, or `wiki_update_index`, a fire-and-forget background task runs `git add -A && git commit && git push`. Leandro clones the same repo locally in Obsidian to browse/edit the wiki by hand; edits are picked up on Ana's next read.

## 8. Data Flows

### 8.1 Reactive (user message → reply)

```
Telegram message arrives
  └─ bot handler
     ├─ verify chat_id == AUTHORIZED_CHAT_ID (drop otherwise)
     ├─ load last 10 chat_history rows for this agent
     ├─ load facts (memory_list_facts)
     ├─ set context tag = 'reactive'
     └─ build CrewAI Task with context
        ├─ LLM turn → may call tools → tool results feed back
        ├─ loop until final answer
        └─ usage_tracker logs each LLM call
     ├─ store (user_msg, reply) in chat_history
     └─ send reply to Telegram
```

Typical: 1–3 LLM turns per user message. Cost on Gemini 2.0 Flash: fractions of a cent.

### 8.2 Proactive (scheduler → push)

Example: morning briefing at 07:00.

```
APScheduler tick (07:00 America/Sao_Paulo)
  └─ briefing job (Ana)
     ├─ check ping_log for today's 'briefing' → skip if already sent
     ├─ insert ping_log row with sent_at = NULL (write-ahead)
     ├─ gather context: today's calendar events + open todos + facts
     ├─ set context tag = 'briefing'
     ├─ run CrewAI Task: "build a pt-BR morning briefing"
     ├─ send result to Telegram (via bot layer)
     └─ UPDATE ping_log set sent_at = now()
```

### 8.3 Catchup (on process startup)

```
on startup:
  for job_kind in ['briefing', 'recap', 'lint']:
    expected_ref_id = compute_current_ref(job_kind)
    if ping_log.already_sent(job_kind, expected_ref_id, agent):
      continue
    if within_catchup_window(job_kind, now):
      run_job_now(job_kind, ref_id=expected_ref_id)
```

**Catchup windows**:

| Job | Catchable? | Window |
|---|---|---|
| `briefing` | yes | Until 12:00 same day |
| `recap` | yes | Until 23:59 same day |
| `pre_event` | **no** | Firing after the event is pointless |
| `todo_sweep` | no | Next hourly tick catches up naturally |
| `lint` | yes | Until next Sunday |

## 9. LLM Abstraction & Cost Tracking

### 9.1 The router

`core/llm/router.py` wraps LiteLLM and provides:

1. Pluggable provider/model selection read from each agent's `SKILL.md` frontmatter.
2. Automatic fallback chain on transient failures (opt-in, ordered list).
3. Per-call usage logging to `llm_usage` — tokens in/out, cost USD, duration, context tag, errors.
4. Context tag propagation through async boundaries via `contextvars.ContextVar`.

### 9.2 Pluggability

Switching Ana from one LLM to another = editing three lines in `SKILL.md`:

```yaml
llm:
  provider: gemini          # → openai, anthropic, deepseek, ...
  model: gemini-2.0-flash   # → gpt-4o-mini, claude-haiku-4-5, ...
  temperature: 0.4
```

Restart the process. Everything else (tools, wiki, memory, scheduler, cost tracker) is provider-agnostic.

Each agent can use a **different** provider. Usage is tracked separately per agent.

### 9.3 Pricing table

`core/llm/pricing.py` — single source of truth. Update when providers change prices.

```python
# USD per 1M tokens. Input and output priced separately.
# VERIFY these numbers on provider pages before deploy.
PRICING = {
    # Anthropic
    "anthropic/claude-haiku-4-5":     {"input": 1.00,  "output": 5.00},
    "anthropic/claude-sonnet-4-5":    {"input": 3.00,  "output": 15.00},
    "anthropic/claude-opus-4-6":      {"input": 15.00, "output": 75.00},

    # OpenAI
    "openai/gpt-4o-mini":             {"input": 0.15,  "output": 0.60},
    "openai/gpt-4o":                  {"input": 2.50,  "output": 10.00},

    # Google
    "gemini/gemini-2.0-flash":        {"input": 0.075, "output": 0.30},
    "gemini/gemini-1.5-pro":          {"input": 1.25,  "output": 5.00},

    # DeepSeek
    "deepseek/deepseek-chat":         {"input": 0.27,  "output": 1.10},
    "deepseek/deepseek-reasoner":     {"input": 0.55,  "output": 2.19},

    # Groq
    "groq/llama-3.3-70b-versatile":   {"input": 0.59,  "output": 0.79},
}

USD_TO_BRL = 5.00  # Update periodically or fetch from an API.
```

### 9.4 Context tags

Every LLM call carries one of these tags so you can see where money is going:

| Tag | Meaning |
|---|---|
| `reactive`   | User sent a message; agent replied |
| `briefing`   | Morning briefing (07:00) |
| `recap`      | Evening recap (21:00) |
| `pre_event`  | Pre-event ping |
| `todo_sweep` | Overdue todo sweep |
| `lint`       | Weekly wiki lint |
| `ingest`     | Agent spontaneously wrote to its wiki during a reactive turn |

Tags are set by the *caller* via a `set_context()` helper that uses a `ContextVar`, so every nested LLM call inherits the tag automatically.

### 9.5 Budget caps

Per-agent caps in SKILL.md frontmatter. The router checks totals from `llm_usage` **before** each LLM call.

Modes:
- **`notify`** — logs a warning and sends a Telegram alert at the boundary crossing (not on every call); the call still proceeds
- **`halt`** — the call refuses with a specific error; the agent sends a hardcoded PT-BR apology

Ana defaults: daily cap US$0.25 (R$1.25), monthly US$6.00 (R$30.00), mode `notify`.

### 9.6 The `/usage` Telegram command

Returns a live SQL-aggregated report, formatted in pt-BR. No LLM call needed — a template fills in the numbers.

Supported forms:

```
/usage              → month-to-date summary (all agents)
/usage today
/usage week
/usage month
/usage ana          → just Ana
/usage ana week
```

Example output:

```
📊 Uso últimos 30 dias

ana:
  requests:     243
  input:        412.000 tokens
  output:        87.000 tokens
  custo total:  US$ 0.89  (R$ 4.45)

  por contexto:
    reactive:    US$ 0.45 (51%)
    briefing:    US$ 0.12 (13%)
    recap:       US$ 0.10 (11%)
    pre_event:   US$ 0.15 (17%)
    lint:        US$ 0.07 (8%)

orçamento mês:   US$ 6.00  (R$ 30.00)
usado:           14.8%  ✅
```

## 10. Reliability

### 10.1 Retry policy

Every external call wrapped with `tenacity`:

- 3 attempts
- Exponential backoff 1s → 2s → 4s, plus random jitter
- Retry **only** on transient errors: 5xx, 429, connection errors, timeouts
- Never retry on 4xx (other than 429)
- Re-raise on final failure so the caller can decide the next step (fallback model, user-facing error, etc.)

### 10.2 Fallback chain

Opt-in per agent via SKILL.md `llm.fallback`. If the primary provider fails after retries, the router tries each fallback in order. Each call (primary and fallback) is still logged separately in `llm_usage`.

Ana's defaults: **Gemini 2.0 Flash → GPT-4o-mini → Claude Haiku 4.5**.

### 10.3 Scheduler catchup

See Section 8.3. Handles missed briefings/recaps/lints when the process was down at the scheduled tick.

### 10.4 Idempotency (`ping_log`)

Composite PK `(kind, ref_id, agent_name)`. Write-ahead pattern:

1. Insert row with `sent_at = NULL`
2. Send the message
3. `UPDATE sent_at = now()`

On startup, rows with `sent_at IS NULL` and a stale `ref_id` are re-sent.

`ref_id` by job:

| Job | `ref_id` format |
|---|---|
| `briefing`   | `YYYY-MM-DD` |
| `recap`      | `YYYY-MM-DD` |
| `pre_event`  | Google Calendar `event_id` |
| `todo_sweep` | `YYYY-MM-DD` (max one sweep message per day) |
| `lint`       | `YYYY-WW` (ISO week) |

### 10.5 User-facing errors (hardcoded pt-BR)

| Cause | Ana's reply |
|---|---|
| LLM down, no fallback | "Desculpa, estou tendo problemas para pensar agora. Me chama de novo em 1 minuto?" |
| Google Calendar auth expired | "Preciso reautorizar seu Google Calendar. Me manda /reauth pra começar." |
| Calendar API 5xx | "Não consegui acessar seu calendário agora. Tentando de novo..." |
| Budget cap hit (halt mode) | "Orçamento diário atingido. Volto amanhã cedinho. Se for urgente, me avisa." |

These strings are hardcoded, not LLM-generated — so Ana can still speak when the LLM is down.

### 10.6 Logging

Structured JSON lines to stdout. One line per significant event. Fields: `ts`, `level`, `agent`, `context`, `event`, `details`. Fly collects stdout automatically; `fly logs -a conexus` tails them.

## 11. Testing

### 11.1 Unit tests (fast, no network)

- `test_pricing.py` — cost calculations across models, zero-token edge case, unknown-model fallback
- `test_usage_tracker.py` — write → read → aggregate
- `test_scheduler_catchup.py` — missed ticks, catchup windows, idempotency write-ahead
- `test_skill_loader.py` — valid/invalid SKILL.md parsing, missing fields
- `test_tools_calendar.py` — each tool with a mocked Google Calendar client
- `test_tools_wiki.py` — read, list, search, write, log append, index update

Target: ~80% coverage of `core/` and `agents/ana/tools.py`. Runs in <3 seconds.

### 11.2 Integration tests (medium, need real API keys)

- One end-to-end reactive turn: canned message → response shape assertion (not exact content — LLM is non-deterministic)
- Real Google Calendar CRUD against a throwaway test calendar
- LLM router with each configured provider (1 small call each), verify usage tracking wrote a row

### 11.3 Manual smoke test

Run after every deploy. See Appendix A.

## 12. Deployment

### 12.1 Fly.io

- Region: `gru` (São Paulo)
- Machine: `shared-cpu-1x`, 256 MB RAM
- Volume: `conexus_data` (1 GB) mounted at `/data`
- Health check: TCP on port 8080 (trivial "ok" endpoint that the process exposes so Fly can detect crashes and restart)
- Deploy strategy: `immediate`

### 12.2 `fly.toml` (sketch)

```toml
app = "conexus"
primary_region = "gru"

[build]
  dockerfile = "deployment/Dockerfile"

[env]
  TZ = "America/Sao_Paulo"
  PYTHONUNBUFFERED = "1"

[[mounts]]
  source = "conexus_data"
  destination = "/data"

[[vm]]
  size = "shared-cpu-1x"
  memory = "256mb"

[deploy]
  strategy = "immediate"

[[services]]
  internal_port = 8080
  protocol = "tcp"
  [[services.tcp_checks]]
    interval = "30s"
    timeout = "5s"
    grace_period = "10s"
```

### 12.3 Dockerfile (sketch)

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

COPY . .

CMD ["python", "main.py"]
```

### 12.4 Secrets

All set via `fly secrets set KEY=value`:

| Secret | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | Bot auth |
| `AUTHORIZED_CHAT_ID` | yes | Whitelist Leandro's Telegram chat |
| `GEMINI_API_KEY` | yes | Default LLM provider |
| `OPENAI_API_KEY` | optional | Fallback LLM |
| `ANTHROPIC_API_KEY` | optional | Fallback LLM |
| `GOOGLE_OAUTH_CLIENT_ID` | yes | Calendar OAuth |
| `GOOGLE_OAUTH_CLIENT_SECRET` | yes | Calendar OAuth |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | yes | Calendar OAuth |
| `GITHUB_WIKI_REPO_URL` | yes | Wiki sync |
| `GITHUB_WIKI_DEPLOY_KEY` | yes | Wiki sync auth (SSH deploy key) |

### 12.5 Google Calendar OAuth bootstrap

`scripts/bootstrap_google.py` is run **once**, locally:

1. Reads `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` from a local `.env`
2. Starts a local callback server on `http://localhost:8765/callback`
3. Opens the browser to Google's consent screen
4. After approval, exchanges the authorization code for a refresh token
5. Prints: `fly secrets set GOOGLE_OAUTH_REFRESH_TOKEN=<token>`

Accept Google's "unverified app" warning (self-authorizing your own calendar against your own OAuth client is safe).

### 12.6 Wiki sync

On process boot:
- If `/data/wiki` is empty → `git clone` the repo using the SSH deploy key
- Else → `git pull`

After every `wiki_write` / `wiki_append_log` / `wiki_update_index`:
- Fire-and-forget background task: `git add -A && git commit -m "<log-line>" && git push origin main`
- On failure: log, retry on next mutation, alert after 5 consecutive failures

## 13. Cost Model (monthly, realistic)

With Gemini 2.0 Flash as the default:

| Line item | Usage estimate | Cost (USD) | Cost (BRL) |
|---|---|---:|---:|
| Fly.io VM (shared-cpu-1x, 256 MB) | 24/7 | Free tier | R$ 0.00 |
| Fly.io volume (1 GB) | Persistent | Free tier | R$ 0.00 |
| Telegram Bot API | Unlimited | Free | R$ 0.00 |
| Google Calendar API | ~500 calls/day | Free | R$ 0.00 |
| GitHub (private repo) | Wiki storage | Free | R$ 0.00 |
| Gemini 2.0 Flash — input (~2M tokens/mo) | ~30 reactive × 2k + 4 scheduled × 1.5k per day | $0.15 | R$ 0.75 |
| Gemini 2.0 Flash — output (~420k tokens/mo) | ~30 × 400 + 4 × 300 per day | $0.13 | R$ 0.65 |
| **Total (Gemini Flash)** | | **~$0.28** | **~R$ 1.40** |

With Claude Haiku 4.5 instead: ~R$ 5–10 / month.

Both comfortably under the R$30 monthly budget, with headroom for Researcher and Code Manager.

## 14. Multi-agent routing (v1)

Explicit prefixes:

- `/ana <message>` → Ana
- `/researcher <message>` → Researcher (when it exists)
- `/code_manager <message>` → Code Manager (when it exists)
- No prefix → default to Ana

v2 candidate: a lightweight router agent that classifies intent and dispatches. Decision deferred until we have ≥2 agents and a feel for the patterns.

## 15. Path to the Team

Adding Researcher (or Code Manager) later should be a 2–4 hour task, not a refactor:

1. `mkdir agents/researcher/`
2. Write `agents/researcher/SKILL.md` — role, goal, tools, LLM, cron, budget
3. Write `agents/researcher/tools.py` — domain-specific tools (e.g., web search via Tavily, RSS reader, URL fetcher)
4. Write `agents/researcher/jobs.py` — scheduled jobs (e.g., daily digest)
5. `fly secrets set` any new API keys the new agent needs
6. `fly deploy`

**What does not change**: LLM router, usage tracker, budget caps, memory core, Telegram bot, scheduler. The new agent's LLM calls show up under `agent_name = 'researcher'` automatically.

## 16. Out of Scope for v1

Explicitly deferred to preserve the weekend deadline:

1. Multi-user support
2. Horizontal scaling or blue/green deploys
3. Full observability stack (Prometheus, Grafana)
4. End-to-end encryption of wiki content beyond git + Fly volume privacy
5. Full automated wiki lint prompt (cron wired, prompt stubbed)
6. MCP-based tool integrations (Ana uses custom Python; MCP evaluated for Researcher/Code Manager in v2)
7. Router/manager agent for multi-agent dispatch
8. CI/CD pipeline
9. `litestream` continuous SQLite replication (daily backup sufficient for v1)

## 17. Open Questions (to revisit after v1 ships)

1. Adopt MCP servers for Researcher (web search, GitHub) and Code Manager (GitHub, code search)?
2. Introduce a router agent, or keep explicit prefixes?
3. Activate the weekly lint with a real prompt, or leave stubbed?
4. Add a `/reauth` Telegram command to re-run Google OAuth without SSH?
5. Switch to `litestream` for continuous SQLite backups?

---

## Appendix A — Manual Smoke Test Checklist (run on every deploy)

### Reactive
- [ ] Send "olá" → Ana replies in pt-BR
- [ ] Send "que horas são?" → Correct São Paulo time
- [ ] Send "o que tenho hoje?" → Lists today's events from real Google Calendar
- [ ] Send "agende reunião teste amanhã às 15h" → Event appears in Google Calendar
- [ ] Send "apaga essa reunião teste" → Ana asks for confirmation before deleting
- [ ] Send "odeio reuniões de segunda de manhã" → Ana updates `wiki/preferences/schedule.md` and appends to `log.md`
- [ ] Send `/usage` → Returns formatted pt-BR cost report

### Proactive
- [ ] Wait for next pre-event ping → Ana pings ~15 min before the event
- [ ] Trigger morning briefing manually (admin command) → Ana sends today's briefing

### Reliability
- [ ] Restart Fly app during the day → No duplicate briefings fire
- [ ] Edit a wiki file locally, git push → Ana reflects the change on next query
- [ ] Set `GEMINI_API_KEY` to invalid temporarily → Fallback to OpenAI works (or clean error if fallback disabled)

### Wiki
- [ ] Check `fly logs` → see `wiki_read index.md` before most queries
- [ ] After a substantive conversation, `log.md` has a new entry with the correct `## [YYYY-MM-DD HH:MM] <kind> | <title>` prefix
- [ ] `git log` in the wiki repo shows autocommits

## Appendix B — One-time Bootstrap Checklist (~90 minutes)

### 1. Accounts (10 min)
- [ ] Create Fly.io account, install `flyctl`, run `fly auth login`
- [ ] Create GitHub account (if you don't have one)

### 2. Telegram bot (5 min)
- [ ] Message `@BotFather` → `/newbot` → name `conexus_ana_bot` → save token
- [ ] Message `@userinfobot` → save your own chat_id

### 3. Google Calendar OAuth (20 min — the slow one)
- [ ] Google Cloud Console → new project "conexus"
- [ ] Enable Google Calendar API
- [ ] OAuth consent screen → External → fill basics
- [ ] Credentials → Create Credentials → OAuth 2.0 Client ID → Desktop app
- [ ] Save `client_id` and `client_secret`
- [ ] Run `python scripts/bootstrap_google.py` locally → approve in browser
- [ ] Copy the refresh token it prints

### 4. LLM API key (5 min)
- [ ] `aistudio.google.com` → Get API key → save
- [ ] (Optional) Also grab keys from `console.anthropic.com` and `platform.openai.com` for fallback

### 5. Wiki repo (5 min)
- [ ] Create private GitHub repo `conexus-ana-wiki`
- [ ] `ssh-keygen -t ed25519 -f wiki_deploy_key`
- [ ] Add public key to repo's Deploy Keys with **write** access

### 6. Fly secrets (10 min)
- [ ] `fly secrets set TELEGRAM_BOT_TOKEN=...`
- [ ] `fly secrets set AUTHORIZED_CHAT_ID=...`
- [ ] `fly secrets set GEMINI_API_KEY=...`
- [ ] `fly secrets set GOOGLE_OAUTH_CLIENT_ID=...`
- [ ] `fly secrets set GOOGLE_OAUTH_CLIENT_SECRET=...`
- [ ] `fly secrets set GOOGLE_OAUTH_REFRESH_TOKEN=...`
- [ ] `fly secrets set GITHUB_WIKI_REPO_URL=git@github.com:you/conexus-ana-wiki.git`
- [ ] `fly secrets set GITHUB_WIKI_DEPLOY_KEY="$(cat wiki_deploy_key)"`

### 7. Deploy (5 min)
- [ ] `fly volumes create conexus_data --region gru --size 1`
- [ ] `fly deploy`
- [ ] `fly logs -a conexus` → watch for "Ana online"
- [ ] Send "olá" to your bot on Telegram → verify reply

### 8. Seed the wiki (15 min)
- [ ] Clone the wiki repo locally, open in Obsidian
- [ ] Write `about/leandro.md` with your profile and current focus
- [ ] Write `about/conexus.md` with company context
- [ ] Write `preferences/schedule.md` with do/don't rules
- [ ] `git push` → Ana picks it up on next query
