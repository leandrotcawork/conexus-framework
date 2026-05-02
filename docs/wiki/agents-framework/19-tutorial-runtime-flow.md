# 19 — Tutorial: End-to-End Runtime Flow

Precise walkthrough of every code path from process start to Telegram reply.
After reading this you can trace any Conexus behaviour to a specific file and
line without needing to grep the codebase.

Cross-links: [[16-tutorial-create-agent]] (agent creation),
[[17-tutorial-create-team]] (team creation), [[18-tutorial-deploy]] (env vars,
Fly.io). Design rationale: [[06-multi-agent-orchestration]] §13-14.

---

## 1. Boot sequence

`main.py` calls `asyncio.run(adapters.telegram_runner.run())`.
`run()` in `adapters/telegram_runner.py:129` executes the following in order:

```
1. load_dotenv()
2. SqliteStore(db_path) — does NOT call init_db() yet
   → store.init_db() is called next, which runs:
       SCHEMA DDL (facts, todos, chat_history, ping_log, llm_usage, failed_sends)
       init_handoff_audit(conn)   — handoff_audit table + idempotent ALTER for session_id
       init_tool_audit(conn)      — tool_audit table + index
3. SSH key injection (_install_ssh_key) + wiki clone/pull (_clone_or_pull)
   → writes ~/.ssh/ana_deploy, ~/.ssh/pesquisador_deploy
   → ssh-keyscan github.com → ~/.ssh/known_hosts
   → git clone / git pull for ANA_WIKI_REPO and KNOWLEDGE_WIKI_REPO
4. WikiStore instances constructed (wiki, knowledge_wiki)
5. UsageTracker(store) + CapChecker(tracker)
6. parse_skill_file("agents/ana/SKILL.md") → SkillDocument
   AnaTools(store, wiki, GoogleCalendarClient())
   registry.register("ana", ana_tools)     → wraps in PythonBackend
   build_runtime("agents/ana/SKILL.md", ...)  → AgentRuntime with handler_cfg
7. parse_skill_file("agents/pesquisador/SKILL.md")
   PesquisadorTools(wiki=knowledge_wiki, llm_synthesis=pesq_llm_synthesis)
   registry.register("pesquisador", pesq_tools)
   build_runtime("agents/pesquisador/SKILL.md", ...) → AgentRuntime
8. TelegramBot (ana) + TelegramBot (pesquisador) constructed
9. ana_app.initialize() / post_init() / delete_webhook() / start()
   ana_app.updater.start_polling(drop_pending_updates=True)
   → "Ana online (@<username>)."
10. pesq_app.initialize() ... start_polling(drop_pending_updates=True)
    → "Pesquisador online (@<username>)."
11. ConexusScheduler(store, tz="America/Sao_Paulo")
    scheduler.add_job(JobSpec("ana", "briefing", "0 7 * * *", ...))
    ... (7 more jobs)
    scheduler.start()
12. await scheduler.catchup()
    → scans ping_log for missed scheduled runs since last boot, re-fires catchable jobs
13. while True: await asyncio.sleep(3600)   ← keeps the event loop alive
```

Key types:
- `SqliteStore` — `src/conexus/core/memory/sqlite_store.py`
- `AgentRegistry` — `src/conexus/core/agent_registry.py`
- `build_runtime` — `src/conexus/cli/runner.py:22`
- `ConexusScheduler`, `JobSpec` — `src/conexus/core/scheduler/scheduler.py`

---

## 2. Single-agent request flow

### Telegram → handler

```
User sends Telegram message
  → python-telegram-bot MessageHandler
  → TelegramBot._message_callback
  → closure: _handle_ana_message(body, prefix, progress)
      = handle_agent_message(_ana_handler_cfg, store, cap_checker, body, progress)
```

`handle_agent_message` lives in `src/conexus/core/agent_handler.py:45`.

### Inside `handle_agent_message`

```python
# 1. Budget cap check (pre-turn)
if cfg.cap:
    r = cap_checker.check(cfg.name, cfg.cap)
    if not r.allowed:
        return cfg.cap_exceeded_msg   # ← early exit

# 2. TrifectaGuard construction (src/conexus/core/agent_handler.py:63-68)
if cfg.tool_tags is None:
    guard = None                        # guard disabled
elif cfg.incoming_handoff is not None:
    guard = TrifectaGuard.from_handoff(cfg.tool_tags, cfg.incoming_handoff)
else:
    guard = TrifectaGuard(cfg.tool_tags)

# 3. Build messages list
history = store.chat_recent(cfg.name, limit=10)
system = cfg.system_prompt + f"\n\nData/hora atual (BRT): {now_brt}"
messages = [
    {"role": "system", "content": system},
    {"role": "user",   "content": "<facts>\n<history>\n<user body>"},
]
store.chat_append(cfg.name, "user", body)   # record user turn up-front

# 4. Tool-calling loop — up to cfg.max_turns iterations
with set_context("reactive"):
    for _turn in range(cfg.max_turns):
        resp, actual_model = await cfg.llm.acall(
            messages=messages,
            tools=cfg.tools_schema,
            tool_choice="auto",
        )
        choice = resp.choices[0]
        msg = choice.message

        if tool_calls:
            messages.append(msg)
            for tc in tool_calls:
                fn_name, fn_args, tc_id = ...

                # Optional Trifecta check
                if guard:
                    guard.check_and_record(fn_name)  # raises TrifectaViolation on block

                # Optional progress notification
                if progress and fn_name in cfg.progress_map:
                    await progress(cfg.progress_map[fn_name])

                result = await cfg.execute_tool(fn_name, fn_args)  # → JSON string

                if cfg.result_max_chars and len(result) > cfg.result_max_chars:
                    result = result[:cfg.result_max_chars] + "\n[... truncado]"

                messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})
            continue   # ← next LLM turn

        # Plain text reply — end of turn
        reply = text_content or "Pronto."
        store.chat_append(cfg.name, "assistant", reply)
        return reply

# Exhausted max_turns with no plain-text reply
store.chat_append(cfg.name, "assistant", cfg.fallback_msg)
return cfg.fallback_msg
```

---

## 3. Tool execution path

`cfg.execute_tool` is a closure over `AgentRegistry.execute_tool`:

```python
# adapters/telegram_runner.py:191-192
async def _ana_execute(name: str, args: dict) -> str:
    return await registry.execute_tool("ana", name, args)
```

Inside `AgentRegistry.execute_tool` (`src/conexus/core/agent_registry.py:37`):

```python
backends = self._backends.get(agent_name)         # list[ToolBackend]
matches = [b for b in backends if name in b.list_tools()]
# collision (>1 match) → error string
return await matches[0].execute(name, args)
```

For a `PythonBackend` (`src/conexus/core/backends/python_backend.py:14`):

```python
fn = getattr(self._tools, tool_name)
result = await fn(**args) if iscoroutinefunction(fn) else fn(**args)
return json.dumps(result, ensure_ascii=False, default=str)
```

The `default=str` catch converts any non-serialisable type (datetime, Path,
etc.) to its string representation instead of raising.

For a `McpStdioBackend` (`src/conexus/core/backends/mcp_stdio_backend.py`):
JSON-RPC 2.0 `tools/call` over the subprocess stdin/stdout pipe, with an
`asyncio.Lock` for id correlation.

---

## 4. TrifectaGuard — taint tracking

`TrifectaGuard` (`src/conexus/core/trifecta/guard.py`) is a stateful per-turn
object. It tracks which `DataClass` values (`untrusted_read`, `private_read`,
`external_write`, `safe`) have been accumulated this turn.

On each tool call, `check_and_record(fn_name)`:

1. Looks up `fn_name` in `tool_tags` dict; falls back to `auto_tag(fn_name)`
   heuristic (`src/conexus/core/trifecta/tags.py:43`).
2. If the tag is `external_write` AND `trust_boundary_cleared is None` AND
   both `untrusted_read` and `private_read` are already in `self._taint`,
   raises `TrifectaViolation`.
3. Otherwise adds the tag to `self._taint`.

The blocker is the "lethal trifecta" exfil path: agent reads untrusted web
content (untrusted_read) + reads private data (private_read) + writes to an
external sink (external_write) — all in one turn.

`TrifectaViolation` is caught in the tool loop and returned as
`{"error": "TrifectaGuard: ..."}` — the LLM sees the error, the turn continues.

To generate a starter `data_classes:` map for a tools file:

```bash
conexus tag suggest agents/myagent/tools.py
```

---

## 5. Budget cap flow

`CapChecker.check(agent_name, cap)` (`src/conexus/core/budget/cap_checker.py`)
reads `UsageTracker` for today's USD spend:

- `on_exceed: notify` → returns `allowed=False`, the call returns `cap_exceeded_msg`.
- `on_exceed: halt` → same immediate block.

Scheduled jobs bypass the cap check by design — they are invoked directly via
`scheduler.add_job` closures that call tools or LLMs directly, not through
`handle_agent_message`.

---

## 6. Multi-agent (team) request flow

`handle_team_message` (`src/conexus/core/agent_handler.py:186`) is the team
entry point. It is stack-based and serial.

### Initialisation

```python
session_id = session_id or f"sess-{uuid.uuid4().hex[:12]}"
store.init_db()
audit_conn = sqlite3.connect(store.db_path)   # single connection for the session
router = HandoffRouter(team, conn=audit_conn, session_id=session_id)
```

Starter agent: `team.manager or team.members[0]`.

### Stack loop

```
stack = [_Frame(starter, initial_msgs, handoff=None, return_on=None)]

while stack:
    frame = stack[-1]
    frame.turns_left -= 1

    all_tools = frame.cfg.tools_schema + build_delegate_schemas(team, frame.name)
    resp = await frame.cfg.llm.acall(messages=frame.messages, tools=all_tools)

    if tool_calls:
        for tc in tool_calls:
            if fn_name.startswith("delegate_to_"):
                # DELEGATION PATH
                target, payload, opts = parse_delegate_call(fn_name, fn_args)
                seed_tags = frame.guard.tainted_with() if frame.guard else set()
                h = Handoff(from_agent=frame.name, to_agent=target,
                            payload=payload, tags=seed_tags, ...)
                # or: frame.last_handoff.next_hop(target) if chaining
                resolved = router.route(h)             # writes to handoff_audit
                child_msgs = trim_transcript(frame.messages, h.context_mode)
                # inject child system prompt if not present
                child_msgs.append({"role": "user", "content": f"Delegated by {frame.name}: ..."})
                frame.messages.append({"role": "tool", ..., "content": {"delegated_to": resolved}})
                stack.append(_make_frame(resolved, child_msgs, h, h.return_on))
                break   # one delegation per parent turn (max_parallel_members=1)
            else:
                # NORMAL TOOL PATH
                guard.check_and_record(fn_name)        # may raise TrifectaViolation
                result = await frame.execute_tool(fn_name, fn_args)
                record_tool_call(audit_conn, ...)      # writes to tool_audit
                frame.messages.append(tool result)
        continue   # next LLM turn for this frame

    # PLAIN TEXT REPLY
    reply = text_content or "Pronto."
    if termination_text in reply:
        store.chat_append(starter, "assistant", reply)
        return reply                                   # ← whole loop ends

    if frame.return_on and frame.return_on in reply:
        stack.pop()
        if stack:
            stack[-1].messages.append(f"[returned from {frame.name}]: {reply}")
        continue

    stack.pop()
    if stack:
        stack[-1].messages.append(f"[returned from {frame.name}]: {reply}")

store.chat_append(starter, "assistant", last_reply)
return last_reply
```

### Key invariants

| Invariant | Enforcement |
|---|---|
| One delegation per parent turn | `break` after first `delegate_to_` (line ~369) |
| Hop limit | `Handoff.next_hop()` raises `ValueError` at `max_hops + 1` |
| Cross-agent Trifecta | `frame.guard.tainted_with()` → `seed_taint` on child guard |
| Tool audit | `record_tool_call` for every non-delegate call |
| Handoff audit | `router.route()` calls `record_handoff` unconditionally |

---

## 7. Handoff audit schema

`src/conexus/core/memory/handoff_audit.py` — table `handoff_audit`:

```sql
CREATE TABLE IF NOT EXISTS handoff_audit (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL,
  session_id      TEXT NOT NULL DEFAULT 'legacy',
  from_agent      TEXT NOT NULL,
  to_agent        TEXT NOT NULL,
  hop_count       INTEGER NOT NULL,
  tags            TEXT NOT NULL,        -- JSON array of DataClass values
  trust_cleared   INTEGER NOT NULL,     -- 1 if trust_boundary_cleared is set
  payload_json    TEXT NOT NULL,        -- full Handoff.model_dump_json()
  outcome         TEXT NOT NULL         -- "routed" | "unknown_target" | "no_match"
);
```

`init_handoff_audit` runs an idempotent `ALTER TABLE` to add `session_id` to
pre-existing tables (see `src/conexus/core/memory/handoff_audit.py:27`).

---

## 8. Tool audit schema

`src/conexus/core/memory/tool_audit.py` — table `tool_audit`:

```sql
CREATE TABLE IF NOT EXISTS tool_audit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  session_id  TEXT NOT NULL,
  agent       TEXT NOT NULL,
  tool        TEXT NOT NULL,
  args_json   TEXT NOT NULL,   -- json.dumps(args, sort_keys=True)
  result      TEXT NOT NULL,
  outcome     TEXT NOT NULL    -- "ok" | "trifecta_blocked"
);
CREATE INDEX IF NOT EXISTS idx_tool_audit_session ON tool_audit(session_id);
```

---

## 9. Replay

After a team session, the audit tables contain a full record. Replay re-runs
the routing decisions against the current registry:

```bash
conexus replay agents/teams/my_team/TEAM_PACK.md \
  --db ./data/conexus.db \
  --session-id sess-abc123def456 \
  --available-agents ana,pm,researcher
```

`replay_session` (`src/conexus/core/team/replay.py:29`):

1. Reads `handoff_audit` rows for `session_id`, ordered by `id`.
2. For each row: reconstructs a `Handoff` and calls `router._resolve(h)`.
3. If `resolved != recorded_to`, records a `ReplayMismatch(kind="route", ...)`.
4. Counts `tool_audit` rows and reports as `tools_replayed`.

`ReplayReport.mismatches` is empty if the current edges produce identical
routing. A non-empty list is a signal to review before deploying.

---

## 10. MCP producer flow

`build_mcp_producer(wiki_root=..., bearer_token=...)` returns a `FastMCP`
instance (`src/conexus/core/mcp/producer.py:36`). The server exposes three
surfaces:

| Surface | Type | Description |
|---|---|---|
| `verify_bearer(token)` | tool | Call after `initialize`; returns `{"ok": true}` or raises |
| `wiki_search(query)` | tool | Literal substring scan over `*.md`, max 20 hits |
| `wiki://{path}` | resource | Raw markdown of a wiki page, sandboxed to `wiki_root` |

Bearer validation uses `hmac.compare_digest` for constant-time comparison
(`producer.py:31`). Path traversal is blocked by checking that
`(root / path).resolve()` starts with `root.resolve()` (`producer.py:75`).

Started with:

```bash
CONEXUS_MCP_TOKEN=secret conexus mcp-server --wiki-root ./data/wiki
```

The CLI handler (`src/conexus/cli/__main__.py:102-109`) calls
`server.run(transport="stdio")`.

---

## 11. Extension cookbook

### Add a tool to an existing agent

1. Add a public method to the tools class (no leading `_`).
2. Add the method name to `tools:` in `SKILL.md`.
3. Add the description to `_tool_schemas`.
4. If TrifectaGuard is enabled for this agent, add the tool to `data_classes:`
   in its `SKILL_PACK.md` (or let `auto_tag` handle it and verify with
   `conexus tag suggest`).
5. Restart.

### Add a new backend (MCP or custom)

```python
from conexus.core.backends.base import ToolBackend

class MyBackend(ToolBackend):
    async def execute(self, tool_name: str, args: dict) -> str:
        ...                        # must return a JSON string
    def list_tools(self) -> list[str]:
        return ["tool_a", "tool_b"]

registry.register_backend("myagent", MyBackend())
```

`AgentRegistry.register_backend` accepts any `ToolBackend` subclass
(`src/conexus/core/agent_registry.py:23`). Tool-name collision across backends
registered to the same agent returns `{"error": "tool collision: ..."}` instead
of silently shadowing.

### Add a new team edge without code

Edit `agents/teams/<name>/TEAM_PACK.md`, add an edge, then validate:

```bash
conexus run-team agents/teams/<name>/TEAM_PACK.md --available-agents a,b,c
```

Replay against a historical session to confirm no regressions:

```bash
conexus replay agents/teams/<name>/TEAM_PACK.md \
  --db ./data/conexus.db --session-id <id> --available-agents a,b,c
```

### Add a scheduled job

1. Write a job factory in `agents/<name>/jobs.py` that returns an async callable.
2. Register with `scheduler.add_job(JobSpec(...))` in `telegram_runner.py`.
3. The scheduler writes to `ping_log` before firing and marks the row on
   success — idempotent across restarts.

---

## 12. Data flow diagram

```
Telegram message
  └─ TelegramBot._message_callback
       └─ _handle_<agent>_message closure
            └─ handle_agent_message(cfg, store, cap_checker, body)
                 ├─ cap_checker.check           [src/conexus/core/budget/cap_checker.py]
                 ├─ TrifectaGuard(cfg.tool_tags) [src/conexus/core/trifecta/guard.py]
                 ├─ store.chat_recent (history)  [src/conexus/core/memory/sqlite_store.py]
                 └─ for turn in max_turns:
                      ├─ TrackedLLM.acall        [src/conexus/core/llm/router.py]
                      │    └─ LiteLLM → Gemini / OpenAI / Anthropic
                      └─ for each tool_call:
                           ├─ guard.check_and_record [trifecta/guard.py]
                           └─ AgentRegistry.execute_tool
                                └─ PythonBackend.execute
                                     └─ tools_obj.<method>(**args)
                                          └─ json.dumps(result)
                 └─ store.chat_append (reply)
                 └─ return reply → Telegram send_message
```

For a team session, replace `handle_agent_message` with `handle_team_message`
and the stack loop described in §6. Each delegation pushes a new frame; each
plain-text reply pops it.
