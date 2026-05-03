# 16 — Tutorial: Create a Single Agent

End-to-end walkthrough for shipping a new Conexus agent from empty directory to
running REPL and passing tests. After completing this tutorial you can add a new
agent without reading framework source code.

Cross-links: [[17-tutorial-deploy]] (wiring into production),
[[18-tutorial-runtime-flow]] (how the loop works inside).

---

## 1. What you are building

A Conexus agent is:

1. A directory under `agents/<name>/` with a `SKILL.md` and a `tools.py`.
2. An optional `jobs.py` for scheduled work.
3. A `tests/` subdirectory.
4. A registration call in `adapters/telegram_runner.py` for the production bot.

The framework does the rest: parses `SKILL.md`, generates LLM tool schemas,
runs the ReAct loop, caps the budget, and routes messages.

---

## 2. Directory layout

```
agents/
  <name>/
    __init__.py        # empty — marks as package
    SKILL.md           # declarative agent definition
    tools.py           # tool implementation class
    jobs.py            # optional scheduled jobs
    tests/
      __init__.py
      conftest.py
      test_<name>_tools.py
```

Look at `agents/ana/` and `agents/pesquisador/` as live examples.

---

## 3. Write SKILL.md

`SKILL.md` is parsed by `src/conexus/core/config/skill_loader.py`. It is a
Markdown file with YAML frontmatter. The framework extracts everything before
the body (the system prompt) automatically.

### Required frontmatter fields

```yaml
---
name: <string>          # agent identifier — matches registration key
role: <string>          # one-line human description
language: pt-BR         # all existing agents use pt-BR
goal: >                 # multi-line goal injected into system prompt
  ...
tools:                  # allow-list; only listed tools are exposed to the LLM
  - tool_name_1
  - tool_name_2
llm:
  provider: gemini
  model: gemini-2.5-flash
  temperature: 0.4
  fallback:
    - { provider: gemini, model: gemini-3-flash-preview }
budget:
  daily_usd: 0.10
  monthly_usd: 3.00
  on_exceed: notify     # or: halt
---
```

### Optional fields

```yaml
prefix: <string>        # command prefix for multi-bot setups (Pesquisador uses "pesq")
llm_synthesis:          # second LLM for heavy synthesis steps
  provider: gemini
  model: gemini-3.1-pro-preview
  temperature: 0.2
schedules:              # cron jobs (see jobs.py section)
  - { kind: weekly_digest, cron: "0 20 * * 0" }
identity:               # Phase 10 — opt-in persistent identity baseline
  enabled: true         # false (default) = no identity, no change to behavior
  blocks:               # named char-budgeted text buffers pinned in system prompt
    user: 500           # int shorthand: {budget_chars: 500}
  facts:
    enabled: true
    inject_recent: 5    # 0 = tool-pull only; >0 = inject N recent facts into prompt
  wiki:
    dir: ./wiki         # relative to SKILL.md or absolute
    inject_index: true  # prepend wiki file list to every call
  history:              # HistoryCompactor defaults shown
    budget_tokens: 4000
    keep_verbatim: 6
    summary_budget: 800
    trigger_pct: 0.80
```

See `agents/ana/SKILL.md` for Ana's complete definition and
`agents/pesquisador/SKILL.md` for Pesquisador's two-LLM setup.

### Stateless worker vs persistent agent

**Stateless worker** — no `identity:` block. This is the correct pattern for task-specific agents (e.g. a researcher that processes a document and returns). No memory overhead, no extra DB tables written.

```yaml
# agents/worker/SKILL.md
---
name: worker
role: document processor
goal: summarize documents on demand
tools: [summarize]
llm: {provider: gemini, model: gemini-2.5-flash}
---
```

**Persistent agent** — add `identity: enabled: true`. The framework automatically:
1. Builds an `IdentityRuntime` from `build_runtime` (`src/conexus/cli/runner.py:62`).
2. Registers `identity.tools` as a second `PythonBackend` in the registry (`src/conexus/cli/__main__.py:82`).
3. Prepends the identity context (blocks + recent facts + wiki index) before the system prompt on every call.
4. Routes history through `HistoryCompactor` instead of the plain `chat_recent(limit=10)` call.

The agent gains built-in tools automatically — no `tools.py` changes needed:

| Tool | What it does |
|------|-------------|
| `memory_get(key)` | Retrieve a fact by key |
| `memory_set(key, value)` | Persist a fact scoped to this agent |
| `memory_list_facts()` | List all known facts |
| `memory_delete(key)` | Remove a fact |
| `block_get(name)` | Read a core-memory block |
| `block_set(name, content)` | Update a block (budget enforced) |
| `block_list()` | List all blocks |
| `wiki_read(path)` | Read a wiki page |
| `wiki_list(folder)` | List wiki files |
| `wiki_search(query)` | Text search across wiki |
| `wiki_write(path, content)` | Write a wiki page |
| `wiki_append_log(kind, title, body)` | Append a log entry |

These are backed by `IdentityTools` (`src/conexus/core/identity/tools.py`) which wraps `SqliteStore`, `BlockStore`, and `WikiStore` — all scoped to the agent's `agent_id` so agents cannot access each other's facts or blocks.

You must add the tool names you want the LLM to call to the `tools:` list in SKILL.md. Example for a fully persistent agent:

```yaml
tools:
  - memory_set
  - memory_get
  - memory_list_facts
  - block_set
  - block_get
  - wiki_read
  - wiki_write
  - wiki_list
  - wiki_search
  # ... plus your domain tools
```

### Body = system prompt

Everything after the closing `---` delimiter is the system prompt body. Keep it
opinionated and direct — the LLM reads it verbatim on every call.

---

## 4. Write tools.py

### Contract

Every `tools.py` must:

1. Define a **tools class** (dataclass or plain class) with public methods. Each
   public method (no leading `_`) whose name appears in `SKILL.md tools:` is
   exposed to the LLM.
2. Return `dict | list | str` from every tool method. The registry serialises
   the return value with `json.dumps(..., ensure_ascii=False, default=str)`
   (see `src/conexus/core/backends/python_backend.py:20`).
3. Export `create_cli_tools(data_dir: str) -> tuple[SqliteStore, <YourTools>]`
   for the CLI runner (see `src/conexus/cli/__main__.py:47`).

### Minimal example

```python
# agents/myagent/tools.py
from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
from conexus.core.memory.sqlite_store import SqliteStore


@dataclass
class MyAgentTools:
    store: SqliteStore

    # ClassVar dict — documents params for schema_gen
    _tool_schemas: ClassVar[dict] = {}

    def greet(self, name: str) -> dict:
        """Say hello. Returns {"message": "..."}.

        Use when the user wants a greeting.
        """
        return {"message": f"Olá, {name}!"}

    def _internal_helper(self) -> None:
        # Private (leading _) — never exposed to LLM
        pass


MyAgentTools._tool_schemas = {
    "greet": {
        "description": "Greets a person by name.",
        "params": {
            "name": {"description": "The person's first name."},
        },
    },
}


def create_cli_tools(data_dir: str) -> "tuple[SqliteStore, MyAgentTools]":
    from pathlib import Path
    store = SqliteStore(Path(data_dir) / "conexus.db")
    store.init_db()
    return store, MyAgentTools(store=store)
```

### Tool schemas — `_tool_schemas`

`schema_gen.generate_tool_schemas(ToolsClass, allowed_names)` reads
`_tool_schemas` to pull per-tool and per-param descriptions. Without it,
descriptions fall back to the method docstring only. See
`src/conexus/core/tools/schema_gen.py` for how the dict is merged.

Structure:

```python
_tool_schemas = {
    "tool_name": {
        "description": "When to call this tool. What it does. What it returns.",
        "params": {
            "param_name": {
                "description": "...",   # injected into the JSON schema
                "enum": ["a", "b"],     # optional, turns param into an enum
            },
        },
    },
}
```

### Error returns

Return a dict with `"error"` key — never raise (an unhandled exception is
caught by `PythonBackend.execute` and returned as `{"error": str(exc)}`):

```python
def wiki_write(self, path: str, content: str) -> dict:
    if not path.endswith(".md"):
        return {"error": "invalid_path",
                "message": "path must end in .md",
                "hint": "append .md to the filename"}
    self.store.write(path, content)
    return {"ok": True, "path": path}
```

---

## 5. Write tests

### conftest.py

All agent test suites share the same three fixtures:

```python
# agents/myagent/tests/conftest.py
from pathlib import Path
import pytest

@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "conexus_test.db"

@pytest.fixture
def tmp_wiki_dir(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    return wiki

@pytest.fixture(autouse=True)
def _env_isolation(monkeypatch):
    for key in [
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "TELEGRAM_BOT_TOKEN", "GOOGLE_OAUTH_REFRESH_TOKEN",
    ]:
        monkeypatch.delenv(key, raising=False)
```

This mirrors `agents/ana/tests/conftest.py` exactly.

### Unit test — tool function

```python
# agents/myagent/tests/test_myagent_tools.py
import pytest
from conexus.core.memory.sqlite_store import SqliteStore
from agents.myagent.tools import MyAgentTools


@pytest.fixture
def tools(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    return MyAgentTools(store=store)


def test_greet_returns_message(tools):
    result = tools.greet(name="Leandro")
    assert result["message"] == "Olá, Leandro!"


def test_greet_missing_name_raises(tools):
    # schema_gen will surface a TypeError as {"error": ...} in production;
    # unit-test the raw method
    import pytest
    with pytest.raises(TypeError):
        tools.greet()
```

### Schema regression test

Add this to catch description regressions:

```python
import json
from conexus.core.tools.schema_gen import generate_tool_schemas
from agents.myagent.tools import MyAgentTools

def test_schema_snapshot(snapshot):
    schemas = generate_tool_schemas(MyAgentTools, ["greet"])
    snapshot.assert_match(
        json.dumps(schemas, indent=2, sort_keys=True),
        "myagent_tools.schema.json",
    )
```

See `agents/ana/tests/test_schema_gen.py` for a live example.

### Run tests

```bash
uv run pytest agents/myagent/tests/ -v
```

---

## 6. CLI invocation

The CLI REPL lets you talk to any agent without Telegram:

```bash
# defaults: CONEXUS_AGENTS_DIR=./agents, CONEXUS_DATA_DIR=./data
uv run python -m conexus.core   # wrong — use the entry point below

# correct:
uv run python -m conexus run agent myagent
# or, if the package is installed:
conexus run agent myagent
```

The `run agent` subcommand (see `src/conexus/cli/__main__.py:96-99`) does:

1. Loads `agents/myagent/SKILL.md` via `parse_skill_file`.
2. Calls `agents/myagent/tools.py:create_cli_tools(data_dir)` to get
   `(store, tools_obj)`.
3. Registers `tools_obj` in an `AgentRegistry`.
4. Calls `build_runtime(skill_path, tools_obj=..., ...)` to produce an
   `AgentRuntime` with an `AgentHandlerConfig`.
5. Enters a `while True: input("> ")` loop, calling
   `handle_agent_message(cfg, store, cap_checker, line)` per turn.

Environment overrides:

| Var | Default | Effect |
|---|---|---|
| `CONEXUS_AGENTS_DIR` | `./agents` | Root of agent directories |
| `CONEXUS_DATA_DIR` | `./data` | SQLite DB + wiki root |
| `GEMINI_API_KEY` | — | Required for Gemini provider |
| `OPENAI_API_KEY` | — | Required for OpenAI provider |

---

## 7. Register in the production bot

To wire the new agent into `adapters/telegram_runner.py` so it runs 24/7 on
Fly.io:

1. **Instantiate tools** — mirror the Ana / Pesquisador blocks (~line 181-232
   in `telegram_runner.py`):

   ```python
   myagent_tools = MyAgentTools(store=store)
   registry.register("myagent", myagent_tools)

   async def _myagent_execute(name: str, args: dict) -> str:
       return await registry.execute_tool("myagent", name, args)
   ```

2. **Build runtime** — call `build_runtime` (`src/conexus/cli/runner.py:22`):

   ```python
   _myagent_runtime = build_runtime(
       "agents/myagent/SKILL.md",
       tools_obj=myagent_tools,
       execute_tool=_myagent_execute,
       tracker=tracker,
       agent_name="myagent",
       system_prompt=myagent_skill.body,
       max_turns=10,
   )
   _myagent_handler_cfg = _myagent_runtime.handler_cfg
   ```

3. **Create a message handler closure**:

   ```python
   async def _handle_myagent_message(body: str, _prefix: str, progress=None) -> str:
       return await handle_agent_message(
           _myagent_handler_cfg, store, cap_checker, body, progress
       )
   ```

4. **Create a `TelegramBot`** with a new token:

   ```python
   myagent_token = os.environ["TELEGRAM_MYAGENT_BOT_TOKEN"]
   myagent_bot = TelegramBot(
       token=myagent_token,
       agent_name="myagent",
       authorized_user_id=authorized_user_id,
       group_chat_ids=group_chat_ids,
       message_handler=_handle_myagent_message,
       usage_command_handler=_handle_usage_cmd,
   )
   myagent_app = myagent_bot.build()
   ```

5. **Start polling** — add the `initialize / post_init / delete_webhook /
   start / updater.start_polling` sequence (same as for Ana and Pesquisador,
   ~lines 353-365).

6. **Add `TELEGRAM_MYAGENT_BOT_TOKEN`** to Fly secrets (see
   [[17-tutorial-deploy]] §4).

---

## 8. Optional: scheduled jobs

Create `agents/myagent/jobs.py`. Each job is a factory that returns an async
callable:

```python
# agents/myagent/jobs.py
from __future__ import annotations
from typing import Callable, Awaitable

def make_weekly_summary_job(tools, send_fn: Callable[[str], Awaitable[None]]):
    async def _job():
        summary = tools.some_method()
        await send_fn(f"Weekly summary: {summary}")
    return _job
```

Register in `telegram_runner.py`:

```python
from agents.myagent.jobs import make_weekly_summary_job
scheduler.add_job(JobSpec(
    "myagent", "weekly_summary", "0 18 * * 5",
    make_weekly_summary_job(myagent_tools, send_to_leandro),
))
```

The scheduler writes to `ping_log` before firing and marks the row on success
— no duplicate fires on restart. See `src/conexus/core/scheduler/scheduler.py`
for `JobSpec` and `ConexusScheduler`.

---

## 9. Checklist

- [ ] `agents/<name>/__init__.py` exists (empty)
- [ ] `agents/<name>/SKILL.md` has all required frontmatter fields
- [ ] `tools.py` exports `create_cli_tools(data_dir) -> (SqliteStore, Tools)`
- [ ] All tool methods return `dict | list | str`
- [ ] `_tool_schemas` populated with descriptions
- [ ] `tests/conftest.py` has `tmp_db_path`, `tmp_wiki_dir`, `_env_isolation`
- [ ] `uv run pytest agents/<name>/tests/` passes
- [ ] `conexus run agent <name>` starts the REPL without errors
- [ ] Telegram token added to `.env` (local) and Fly secrets (production)
- [ ] Agent registered in `telegram_runner.py`

**If using identity baseline (`identity: enabled: true`):**

- [ ] `identity.blocks` names are declared in SKILL.md frontmatter before first use
- [ ] Identity tool names (`memory_set`, `block_set`, etc.) are listed in `tools:` allow-list
- [ ] `build_runtime` receives the `store` kwarg (required for identity wiring — `src/conexus/cli/runner.py:34`)
- [ ] `wiki.dir` path exists or is auto-created (framework creates it via `mkdir(parents=True, exist_ok=True)`)
- [ ] `summarize_fn` is wired if token-budget compaction is desired (set by `build_runtime` automatically from `identity.history` when store is provided)
