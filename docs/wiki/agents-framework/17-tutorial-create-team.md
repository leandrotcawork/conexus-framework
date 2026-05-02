# 17 — Tutorial: Create a Team

End-to-end walkthrough for declaring a multi-agent team, wiring it into the
runtime, and verifying it with the CLI replay tool. After this tutorial you
can ship a new team without reading `src/conexus/core/team/` source code.

Prerequisites: at least two agents already exist (see [[16-tutorial-create-agent]]).
Cross-links: [[18-tutorial-runtime-flow]] (the team loop internals),
[[06-multi-agent-orchestration]] §13-14 (design rationale).

---

## 1. What a team is

A team is a set of named agents that can delegate tasks to each other during a
single conversation turn. The runtime is a **stack-based serial loop**
(`handle_team_message` in `src/conexus/core/agent_handler.py:186`):

- Only one agent runs at a time (`max_parallel_members=1` in Phase 9).
- An agent calls `delegate_to_<sibling>` as a regular LLM tool call.
- The runtime pushes a new stack frame for the child agent, runs it, and pops
  it when the child returns.
- The whole session is recorded in `handoff_audit` and `tool_audit` for replay.

---

## 2. TEAM_PACK.md schema

A team is declared as a Markdown file with YAML frontmatter. The parser is
`parse_team_pack()` in `src/conexus/core/team/team_pack.py:49`. The canonical
example is `agents/teams/product_team/TEAM_PACK.md`.

### Full schema

```yaml
---
name: my_team             # team identifier
version: 0.1.0            # semver

manager: pm               # optional: first agent to receive every request;
                          # must be in members. Fallback target when no edge matches.
members:
  - ana
  - pm
  - researcher

edges:
  # explicit target: route to 'pm' when task.kind == 'plan'
  - {from: ana, to: pm,         when: "task.kind == 'plan'"}
  # explicit target: condition on nested field
  - {from: pm,  to: researcher, when: "task.kind == 'research'"}
  # auto: true — first auto edge from sender wins (no condition evaluated)
  - {from: researcher, to: pm, auto: true}

budget:
  team_daily_usd: 1.00
  shares:                 # must sum to 1.0 (tolerance ±0.01)
    ana: 0.20
    pm:  0.40
    researcher: 0.40
  on_share_exceeded: notify  # notify | halt_member | borrow_from_pool

policy:
  trifecta_enforcement: strict  # strict | warn | off
  max_hops: 5                   # hard cap across the full session
  max_turns: 20                 # per-frame LLM turns
  max_parallel_members: 1       # Phase 9: serial-only; gate for future parallelism
  termination_text: "DONE"      # any reply containing this string ends the loop

deployment:               # optional per-member hints (informational)
  ana: cloud
  pm: cloud
  researcher: cloud
---

# Body — used as documentation only

Describe the team purpose here.
```

### Pydantic models

| Model | File | Key constraint |
|---|---|---|
| `TeamBudget` | `team_pack.py:9` | `on_share_exceeded` literal |
| `TeamPolicy` | `team_pack.py:15` | `max_parallel_members >= 1` validated |
| `TeamPackFrontmatter` | `team_pack.py:30` | all fields above |
| `TeamPackDocument` | `team_pack.py:41` | `frontmatter + body + pack_dir` |

---

## 3. Edges and routing

`HandoffRouter` (`src/conexus/core/team/handoff_router.py:24`) resolves the
destination agent in this order (see `_resolve`, line 45):

1. **Explicit `to_agent`** — if the LLM passes a non-`"auto"` target and the
   agent is a team member, use it directly.
2. **`auto: true` edge** — first edge from `edges_from(sender)` with
   `auto: true` wins, no condition evaluated.
3. **`when:` edge** — first edge from sender where the `when` expression
   evaluates truthy against `handoff.payload`. Evaluated with a safe AST
   walker (no `eval()`) — allowed: comparisons, bool ops, attribute access on
   `task`, literals, tuples, lists. Blocked: function calls, subscripts,
   dunders.
4. **Manager fallback** — if `registry.manager` is set, route there.
5. **Raise** — `ValueError("no edge match and no manager")`.

### `when:` expression reference

The expression runs against `task` bound to `payload.get("task", {})` via a
`_Box` read-only attribute-access wrapper. Examples:

```yaml
when: "task.kind == 'research'"         # string equality
when: "task.priority > 2"               # numeric comparison
when: "task.kind in ('plan', 'review')" # membership
when: "task.urgent and task.kind == 'deploy'"  # boolean and
```

`task` maps to whatever the LLM passes as the `task` dict in the
`delegate_to_<agent>` call.

---

## 4. Budget cascader

`BudgetCascader` (`src/conexus/core/team/budget_cascader.py:19`) enforces per-
member shares against a shared pool. Three policies:

| `on_share_exceeded` | Behaviour |
|---|---|
| `notify` | `check_and_debit()` returns `False`; the loop logs but does not halt the member |
| `halt_member` | Member is added to `_halted`; subsequent calls raise `ShareExceeded` |
| `borrow_from_pool` | Charge anyway if `pool_remaining() >= cost`; `False` only when pool exhausted |

To wire `BudgetCascader` in the team call site:

```python
from conexus.core.team.budget_cascader import BudgetCascader, BudgetPolicy
from conexus.core.team.team_pack import parse_team_pack

doc = parse_team_pack("agents/teams/my_team/TEAM_PACK.md")
budget = doc.frontmatter.budget
cascader = BudgetCascader(
    team_daily_usd=budget.team_daily_usd,
    shares=budget.shares,
    policy=BudgetPolicy(budget.on_share_exceeded),
)
```

`handle_team_message` does not call `BudgetCascader` directly today — it uses
per-agent `CapChecker` configured from each agent's SKILL.md budget. The
`BudgetCascader` API is available for callers that want shared-pool enforcement
on top of individual caps.

---

## 5. Wire `handle_team_message`

```python
from conexus.core.agent_handler import AgentHandlerConfig, handle_team_message
from conexus.core.budget.cap_checker import CapChecker
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry
from conexus.cli.runner import build_runtime

# 1. Load and validate the pack
available = {"ana", "pm", "researcher"}
doc = TeamLoader(available).load("agents/teams/my_team/TEAM_PACK.md")
team = TeamRegistry(doc)

# 2. Build one AgentHandlerConfig per member
#    Each member needs its own tools, tracker, and runtime
configs: dict[str, AgentHandlerConfig] = {
    "ana": _ana_runtime.handler_cfg,
    "pm": _pm_runtime.handler_cfg,
    "researcher": _researcher_runtime.handler_cfg,
}

# 3. Shared store + cap_checker
store = SqliteStore("./data/conexus.db")
cap_checker = CapChecker(tracker)

# 4. Run
reply = await handle_team_message(
    team=team,
    configs=configs,
    store=store,
    cap_checker=cap_checker,
    body="Plan and research microservices best practices",
    session_id=None,   # auto-generated as sess-<12hex> when None
)
```

`handle_team_message` signature (`src/conexus/core/agent_handler.py:186`):

```python
async def handle_team_message(
    *,
    team: TeamRegistry,
    configs: dict[str, AgentHandlerConfig],
    store: SqliteStore,
    cap_checker: CapChecker,
    body: str,
    session_id: str | None = None,
    progress: Any = None,
) -> str:
```

---

## 6. `delegate_to_<agent>` tool

The LLM discovers delegation tools automatically. `build_delegate_schemas`
(`src/conexus/core/team/delegate_tool.py:14`) generates one OpenAI function
schema per sibling member:

```json
{
  "type": "function",
  "function": {
    "name": "delegate_to_researcher",
    "description": "Delegate sub-task to teammate 'researcher'.",
    "parameters": {
      "type": "object",
      "properties": {
        "task": {"type": "object", "description": "Free-form payload describing the sub-task."},
        "context_mode": {"type": "string", "enum": ["full", "last_message", "summary"]},
        "return_on": {"type": "string"}
      },
      "required": ["task"]
    }
  }
}
```

Parameters:

| Param | Required | Default | Meaning |
|---|---|---|---|
| `task` | yes | — | Arbitrary dict describing the sub-task; `task.*` is what `when:` expressions evaluate against |
| `context_mode` | no | `"summary"` | How much of the parent's transcript the child sees: `full` / `last_message` / `summary` |
| `return_on` | no | `None` | Child reply containing this string pops the child frame and returns control to parent |

### `context_mode` reference

`trim_transcript` (`src/conexus/core/team/transcript.py:5`):

| Mode | Child sees |
|---|---|
| `full` | Full copy of parent's message list |
| `last_message` | Only the last non-system message |
| `summary` | One synthetic system message: `"Transcript summary: N prior message(s) elided"` |

---

## 7. Termination and return

A team session ends when any of these conditions fires (checked in
`handle_team_message`, lines 397-410):

1. **`termination_text`** — any reply containing the text (default `"DONE"`)
   ends the entire loop immediately; the reply is stored in `chat_history` for
   the starter agent.
2. **`return_on` text** — if `frame.return_on` string appears in the child's
   reply, the child frame is popped and the parent receives
   `[returned from <child>]: <reply>` as a user message.
3. **Plain text, no `return_on`** — child frame is popped, parent receives
   the same `[returned from <child>]: <reply>` message and continues.
4. **`max_turns` exhausted** — frame is silently popped.
5. **Stack empty** — `last_reply` (the most recent text reply) is returned.

---

## 8. TeamLoader validation rules

`TeamLoader(available_agents: set[str]).load(pack_path)` raises `ValueError`
when (verified in `src/conexus/core/team/team_loader.py`):

| Rule | Error message |
|---|---|
| Member not in `available_agents` | `"unknown member: <name>"` |
| `manager` not in `members` | `"manager '<name>' not in members"` |
| Shares do not sum to 1.0 (±0.01) | `"budget shares must sum to 1.0 (got <n>)"` |
| Share key not in `members` | `"share for unknown member(s): ['<name>']"` |

---

## 9. CLI validation

```bash
# Validate pack against a list of agents (dry run only — does not execute)
conexus run-team agents/teams/my_team/TEAM_PACK.md \
  --available-agents ana,pm,researcher
```

Output on success: `loaded team my_team: ['ana', 'pm', 'researcher']`

See `src/conexus/cli/__main__.py:146-155`.

---

## 10. Session replay

After a session runs, replay it against a (possibly updated) registry to
detect routing regressions before deploying new edges:

```bash
conexus replay agents/teams/my_team/TEAM_PACK.md \
  --db /data/conexus.db \
  --session-id sess-abc123def456 \
  --available-agents ana,pm,researcher
```

Output:

```
handoffs_replayed: 3
tools_replayed:    7
mismatches: none
```

A `route` mismatch means the current edges would route a recorded handoff
differently — review before deploying. See `src/conexus/core/team/replay.py:29`
for `ReplayReport` and `ReplayMismatch` types.

---

## 11. Cross-agent Trifecta taint

When an agent with `tool_tags` set delegates to another, the parent's current
taint set is propagated via `TrifectaGuard.tainted_with()` and seeded into the
child's guard via `TrifectaGuard.from_handoff()` (see
`src/conexus/core/trifecta/guard.py:36`).

This means: if `ana` accumulated `untrusted_read` taint by calling `web_fetch`,
and then delegates to `pm`, `pm` inherits that taint. An `external_write` call
by `pm` in the same session is blocked unless `trust_boundary_cleared` is set.

To explicitly clear the boundary (operator-level decision):

```python
handoff = Handoff(
    from_agent="ana",
    to_agent="pm",
    payload={"task": {...}},
    trust_boundary_cleared="reviewed-by-operator-2026-05-01",
)
```

The `trust_boundary_cleared` field is a `str | None`; a non-empty string bypasses
the exfil check in `TrifectaGuard.check_and_record`
(`src/conexus/core/trifecta/guard.py:61-72`). The reason string is audited.

---

## 12. Reference team

`agents/teams/product_team/TEAM_PACK.md` is the canonical 3-member example:

- `pm` is manager (receives all requests).
- Edge `ana → pm` when `task.kind == 'plan'`.
- Edge `pm → researcher` when `task.kind == 'research'`.
- Edge `researcher → pm` with `auto: true` (researcher always returns to pm).
- Budget pool $1.00/day, shares 20/40/40, policy `notify`.
- `termination_text: "DONE"`.

---

## 13. Checklist

- [ ] `agents/teams/<name>/TEAM_PACK.md` created with all required fields
- [ ] All `members` exist as runnable agents (see [[16-tutorial-create-agent]])
- [ ] Shares sum to 1.0 (±0.01)
- [ ] `manager` (if set) is in `members`
- [ ] `conexus run-team <pack> --available-agents <csv>` prints "loaded team..."
- [ ] At least one `when:` edge manually verified in a Python REPL (see §3)
- [ ] `handle_team_message` wired with one `AgentHandlerConfig` per member
- [ ] Session ID logged; `conexus replay` passes with no mismatches after each edge change
