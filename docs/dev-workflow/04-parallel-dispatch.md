# 04 — Parallel Dispatch

> Subagents run in parallel only when slices are truly independent. Wrong
> parallelism produces merge conflicts, duplicated logic, and silent
> divergence (Cognition's Flappy Bird problem).

## Independence checklist

A pair of slices is parallel-safe **iff all of**:

- [ ] No shared file (read OR write).
- [ ] No shared symbol introduced or renamed.
- [ ] No shared dependency added to `pyproject.toml`.
- [ ] No shared test fixture being modified.
- [ ] No ordering constraint stated in the plan.

Fail any → run sequentially.

## Dispatch shapes

**Single-message N calls** — true parallel, fastest:

```
Agent({ description: "Slice A", prompt: "..." })
Agent({ description: "Slice B", prompt: "..." })
Agent({ description: "Slice C", prompt: "..." })
```
(All in one message, one tool block.)

**Sequential** — when independence fails:

Dispatch slice A. Wait. Read result. Dispatch slice B with A's diff in context.

**Fan-out / fan-in** — for read-heavy research:

Dispatch N read-only research agents in parallel; synthesise their reports
yourself; dispatch one write agent with the synthesis.

## Per-subagent prompt template

```
Context: <which file, which spec section, current branch>
Task: <single TDD slice — write test, fail, implement, pass, commit>
Constraints:
  - Touch only: <file list>
  - Do not modify: <file list of off-limits files>
  - Must pass: <command>
Done when: <observable success condition>
Report: diff + test output + commit SHA
```

Keep prompts under 300 words. Subagents do not need backstory; they need scope.

## Monitoring

For >3 parallel subagents, run them background (`run_in_background: true`)
and watch via Monitor on a control file (e.g., `git status`). Don't poll.

## Conflict resolution

If two subagents touch the same file (independence check missed something):

1. Reject the later commit.
2. Re-dispatch the rejected slice with the merged file as context.
3. Update independence checklist for the next phase.

## Anti-patterns

- "Dispatch 8 subagents to refactor 8 files" without checking imports — common cascade.
- "Let subagent decide what to touch." Tightly scope; subagents are not architects.
- "Reuse one subagent across slices via SendMessage." Fine for follow-ups, not for fan-out — fresh agent per slice keeps context clean.
