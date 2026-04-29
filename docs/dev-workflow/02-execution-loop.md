# 02 — Execution Loop

> One pass per phase. Phases come from spec / migration plan. Each pass leaves
> green tests, a clean diff, an updated wiki, and one commit per task.

## Loop

```
┌─ KICKOFF (Sonnet) ───────────────────────────────────────────────┐
│  Read phase tasks from plan. Confirm scope. Carve into           │
│  independent slices.                                             │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌─ CODEX PRE-VALIDATION (codex:rescue) ────────────────────────────┐
│  Submit phase plan + spec link. Reject any task codex flags as   │
│  ambiguous, unsafe, or out-of-spec. See 03-codex-validation.md.  │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌─ PARALLEL DISPATCH (Sonnet subagents) ───────────────────────────┐
│  For each independent slice: dispatch subagent with TDD prompt.  │
│  Use single message with N tool calls when slices are truly      │
│  independent (see 04-parallel-dispatch.md).                      │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌─ INTEGRATE ──────────────────────────────────────────────────────┐
│  Pull subagent diffs. Run full test suite. Resolve any merge     │
│  contention (rare if dispatch was scoped right).                 │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌─ /simplify (Sonnet, may escalate) ───────────────────────────────┐
│  Run /simplify skill on every changed code file. Accept or       │
│  reject suggestions. Re-run tests after.                         │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌─ /caveman:compress on prompts ───────────────────────────────────┐
│  For every changed prompt file (SKILL.md fragments,              │
│  prompt templates, system prompts in code), run                  │
│  /caveman:compress to cut tokens without losing substance.       │
│  Re-run any eval that exercises that prompt.                     │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌─ WIKI UPDATE (wiki-keeper subagent) ─────────────────────────────┐
│  Dispatch wiki-keeper with the phase trigger description.        │
│  Accept its diff or send back for revision.                      │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌─ PHASE REVIEW (Opus, code-reviewer subagent) ────────────────────┐
│  Review whole phase diff against the plan. Sign off or list      │
│  blockers. Fix blockers; re-review only the deltas.              │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌─ CHECKPOINT ─────────────────────────────────────────────────────┐
│  Update .brain/ via nexus:nexus-checkpoint. Push branch. Open    │
│  draft PR if branch lifetime > 1 day.                            │
└──────────────────────────────────────────────────────────────────┘
```

## Per-task discipline (inside dispatch)

Every code task = TDD:

1. Write failing test
2. Run test, observe failure with expected message
3. Minimal implementation
4. Run test, observe pass
5. Run full file's test suite
6. Commit (Conventional Commits format)

If a task lacks a meaningful test (pure config / docs), skip TDD but keep
the commit-per-step discipline.

## Skip rules

- **Skip /simplify** if no code changed (docs-only phase).
- **Skip /caveman:compress** if no prompt-bearing files changed.
- **Never skip codex pre-validation** for a phase that touches >1 module.
- **Never skip wiki-keeper** for a phase that changes public surface.
- **Never skip Opus phase review.**

## Failure modes

| Symptom                          | Action                                                          |
|----------------------------------|-----------------------------------------------------------------|
| Subagent returns failing tests   | Re-dispatch with more context; if 2 fails, escalate to Opus     |
| Codex disagrees with plan        | Read codex output; either edit plan or write rebuttal in PR     |
| /simplify suggestion breaks tests| Reject; commit working code                                     |
| wiki-keeper invents content      | Reject diff; sharpen subagent prompt; re-dispatch               |
| Opus review finds blocker        | Open follow-up task in same phase; do not advance phase         |
