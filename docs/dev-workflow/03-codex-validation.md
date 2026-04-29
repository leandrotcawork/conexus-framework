# 03 — Codex Validation

> `codex:rescue` is a separate runtime (GPT-5 family) wired as a Claude Code
> subagent. Use it as an independent reviewer, not a co-author.

## When to call codex

Mandatory:

1. **Pre-phase plan validation.** Before kicking off any phase that touches
   more than one module, submit the phase plan + linked spec. Codex looks for
   spec drift, missing tasks, type mismatches, infeasible orderings.
2. **Architectural decisions where target arch and v2 spec disagree.** Codex
   arbitrates; if it sides with target arch, update spec; if v2, log the
   override in the phase plan.
3. **Persistent test failures (≥3 retries).** Hand the failing test + the
   relevant code window. Codex often spots root causes Claude tunneled past.

Optional:

- Cross-file refactor diffs > 200 LOC.
- Performance hot-paths (`handle_agent_message`, cache prefix builder).
- Security-sensitive code (TrifectaGuard, MCP auth, OAuth path when it lands).

## When NOT to call codex

- Single-file mechanical edits.
- Doc-only commits.
- Test-only commits (write a test, watch it fail, fix it; codex round-trip is overhead).
- Anything Sonnet completed cleanly on first try.

## Calling pattern

```
Agent({
  description: "Codex pre-phase validation",
  subagent_type: "codex:codex-rescue",
  prompt: "<paste-phase-plan> + <link-to-spec>. Validate: spec coverage, task ordering, type consistency, missing prerequisites. Return blockers and a confidence rating."
})
```

## Decision matrix

| Codex output                  | Action                                                       |
|-------------------------------|--------------------------------------------------------------|
| "Plan looks correct"          | Proceed to dispatch                                          |
| "Concern X — but proceed"     | Note in phase plan, monitor during execution                 |
| "Blocker X — do not proceed"  | Fix or rebut. Rebuttals go in plan as `## Codex disagreement`|
| Empty / vague output          | Re-prompt with sharper question; if still vague, ignore      |

## Logging

Every codex call: timestamp + prompt + verdict in
`docs/superpowers/plans/<phase>.md` under a `## Codex log` section. Future
sessions need to see what was asked and answered.
