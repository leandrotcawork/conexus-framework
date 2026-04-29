# 01 — Model Routing

> Pick the cheapest model that can do the job correctly. Escalate on signal,
> not on instinct.

## Tiers

| Tier   | Model              | Use for                                                                 |
|--------|--------------------|-------------------------------------------------------------------------|
| Cheap  | Haiku (claude-haiku-4-5 or current) | Mechanical refactors (rename, move, import-fix), single-file edits, doc edits where structure is given, applying `/simplify` or `/caveman:compress` to a known target |
| Default| Sonnet (claude-sonnet-4-7 or current) | TDD task execution, schema-gen edits, registry wiring, MCP adapter work, most subagent dispatches |
| Strong | Opus (claude-opus-4-7 or current)   | Phase reviews, cross-file architectural changes, debugging non-obvious failures, designing new primitives, codex-disagreement arbitration |

## Rules

1. **Default = Sonnet.** No model selection means Sonnet.
2. **Subagents run on Sonnet** unless their definition pins a model. `wiki-keeper` is pinned to Sonnet by design.
3. **Phase reviews run on Opus.** Always. Phase review = the gate at end of every phase in `02-execution-loop.md`.
4. **Mechanical-only tasks may run on Haiku** when the task is described in full (file list + exact transformation). Save tokens; do not save thinking.
5. **Escalate to Opus when:**
   - Two retries on Sonnet failed with the same error
   - Codex flagged an architectural risk
   - Spec ambiguity surfaces during execution
   - Test that should pass is failing for a reason you cannot explain in one sentence
6. **Never downgrade after escalation** in the same task.

## Anti-patterns

- "Run everything on Opus to be safe." Burns budget without measurable quality lift.
- "Use Haiku for the whole phase." Phase review is non-negotiably Opus.
- "Pin the subagent model in the prompt." Pin it in the subagent definition file so every dispatcher inherits.

## Cost reality check

Track per-phase: total turns × tokens × tier. If Sonnet > 80% of phase cost,
that's expected. If Opus > 30%, you over-escalated; review which calls could
have stayed on Sonnet.
