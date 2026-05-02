# V2 Execution Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a professional engineering workflow for executing Conexus framework v2 (Phases 6–9). Defines model routing, parallel subagent dispatch, prompt/code compression, automated codex validation, and a self-maintaining wiki — all wired so the next phase can be executed by sub-agents with minimal coordination overhead.

**Architecture:** Operator-driven loop. Per phase: (1) plan slice → (2) codex pre-validation → (3) parallel TDD subagents (Haiku/Sonnet) → (4) Opus phase review → (5) `/simplify` pass on code → (6) `/caveman:compress` pass on prompt files → (7) wiki-keeper subagent updates `docs/wiki/agents-framework/*` → (8) commit + checkpoint. Lightweight. Reuses existing skills (`codex:rescue`, `simplify`, `caveman:caveman`, `caveman:compress`, `nexus:*`). Adds one new custom subagent (`wiki-keeper`) and three policy docs.

**Tech Stack:** Markdown subagent files (Claude Code agents format), `.claude/agents/`, `.claude/commands/`, existing skills (caveman, simplify, codex, nexus), Python 3.11 + `uv` for tests/lint, git for checkpoint discipline.

---

## File Structure

| Path | Purpose |
|------|---------|
| `.claude/agents/wiki-keeper.md` | Custom subagent: detects code+spec drift, updates relevant `docs/wiki/agents-framework/*.md` partition |
| `docs/dev-workflow/README.md` | Index of dev workflow policies |
| `docs/dev-workflow/01-model-routing.md` | Which model picks which task class. Examples + escalation rules |
| `docs/dev-workflow/02-execution-loop.md` | Per-phase execution loop template (kickoff → parallel dispatch → review → simplify → wiki → commit) |
| `docs/dev-workflow/03-codex-validation.md` | When and how to use `codex:rescue` for plan + diff review |
| `docs/dev-workflow/04-parallel-dispatch.md` | Playbook for safe parallel subagent dispatch (independence checks, conflict avoidance) |
| `docs/dev-workflow/05-quality-gates.md` | Mandatory gates: pytest, ruff, eval suite, simplify, caveman pass |
| `CLAUDE.md` (modify) | Reference dev-workflow index so future sessions discover it |

Each file has one responsibility; together they form the workflow contract. No code is added by this plan — output is documentation + one subagent definition that codifies how implementation work happens.

---

## Task 1: Create wiki-keeper subagent

**Files:**
- Create: `.claude/agents/wiki-keeper.md`

- [ ] **Step 1: Verify `.claude/agents/` exists**

Run: `ls .claude/agents 2>/dev/null || mkdir -p .claude/agents && ls .claude/agents`
Expected: directory exists, empty.

- [ ] **Step 2: Write the subagent definition**

Create `.claude/agents/wiki-keeper.md`:

```markdown
---
name: wiki-keeper
description: Use when a code change, spec edit, or phase completion may have invalidated content in `docs/wiki/agents-framework/*.md`. Detects drift between code/specs and the wiki, updates the relevant partition file with citations, never invents content. Read-mostly; writes only to `docs/wiki/agents-framework/*.md`. Should be invoked after every phase review and after any spec edit.
tools: Read, Glob, Grep, Edit, Write, Bash
model: sonnet
---

# wiki-keeper

You maintain `docs/wiki/agents-framework/*.md` so it stays a faithful map of
the codebase + specs. You are read-mostly. You only write to wiki files.

## Inputs the caller gives you

- A short trigger description (e.g. "Phase 6.2 done: core/ moved to src/conexus/core/").
- Optional: list of changed files.

## Your loop

1. Read `docs/wiki/agents-framework/00-index.md` to map partitions.
2. Read every partition that the trigger touches.
3. Check the relevant code/spec — open files, search refs.
4. Diff: what does the wiki claim vs what the code says today?
5. Decide:
   - **No drift** → report "no update needed", exit.
   - **Stale fact** → edit wiki section, cite the file/line you verified.
   - **New surface** → add a section; update `00-index.md` if a new partition is justified.
6. Run `git diff docs/wiki/` and report the diff plus reasoning.

## Hard rules

- NEVER invent code behavior. If you cannot verify a claim by reading code or
  spec, do not write it.
- NEVER edit anything outside `docs/wiki/agents-framework/`.
- NEVER delete a partition without explicit operator approval.
- Cite source file paths inline (`see core/agent_handler.py:42`) when adding
  technical claims.
- Match existing wiki tone: technical, opinionated, citation-heavy.
- Keep partition reading order intact (`00-index.md` reading-order section).

## Output format

Return:

1. List of wiki files changed.
2. One-line rationale per change.
3. Unified diff (`git diff docs/wiki/`).
4. Suggested commit message (Conventional Commits, scope: `wiki`).
```

- [ ] **Step 3: Smoke test the subagent**

Dispatch (from main agent):
```
Agent({
  description: "Wiki-keeper smoke test",
  subagent_type: "wiki-keeper",
  prompt: "Trigger: 2026-04-29-conexus-framework-v2.md spec just landed. Check whether docs/wiki/agents-framework/14-conexus-target-architecture.md mentions v2 or needs a cross-reference. Report only — do not write yet."
})
```
Expected: subagent reads index + partition 14 + new spec, returns "no drift" OR a proposed edit with diff.

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/wiki-keeper.md
git commit -m "feat(workflow): add wiki-keeper subagent for docs drift detection"
```

---

## Task 2: Document model routing policy

**Files:**
- Create: `docs/dev-workflow/README.md`
- Create: `docs/dev-workflow/01-model-routing.md`

- [ ] **Step 1: Create dev-workflow index**

Create `docs/dev-workflow/README.md`:

```markdown
# Dev Workflow

Operational policies for executing Conexus framework work. Applies to every
implementation session. Read once per session; cited from per-phase plans.

| # | File | Topic |
|---|------|-------|
| 01 | [model-routing.md](01-model-routing.md) | Which model handles which task class |
| 02 | [execution-loop.md](02-execution-loop.md) | Per-phase execution loop template |
| 03 | [codex-validation.md](03-codex-validation.md) | Codex rescue subagent — when & how |
| 04 | [parallel-dispatch.md](04-parallel-dispatch.md) | Safe parallel subagent dispatch |
| 05 | [quality-gates.md](05-quality-gates.md) | Mandatory pre-commit gates |

Last revised 2026-04-29.
```

- [ ] **Step 2: Write model routing policy**

Create `docs/dev-workflow/01-model-routing.md`:

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add docs/dev-workflow/README.md docs/dev-workflow/01-model-routing.md
git commit -m "docs(workflow): add dev-workflow index + model routing policy"
```

---

## Task 3: Document per-phase execution loop

**Files:**
- Create: `docs/dev-workflow/02-execution-loop.md`

- [ ] **Step 1: Write the loop template**

Create `docs/dev-workflow/02-execution-loop.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/dev-workflow/02-execution-loop.md
git commit -m "docs(workflow): document per-phase execution loop"
```

---

## Task 4: Document codex validation policy

**Files:**
- Create: `docs/dev-workflow/03-codex-validation.md`

- [ ] **Step 1: Write the validation policy**

Create `docs/dev-workflow/03-codex-validation.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/dev-workflow/03-codex-validation.md
git commit -m "docs(workflow): add codex validation policy"
```

---

## Task 5: Document parallel dispatch playbook

**Files:**
- Create: `docs/dev-workflow/04-parallel-dispatch.md`

- [ ] **Step 1: Write the playbook**

Create `docs/dev-workflow/04-parallel-dispatch.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/dev-workflow/04-parallel-dispatch.md
git commit -m "docs(workflow): add parallel dispatch playbook"
```

---

## Task 6: Document quality gates

**Files:**
- Create: `docs/dev-workflow/05-quality-gates.md`

- [ ] **Step 1: Write quality gates**

Create `docs/dev-workflow/05-quality-gates.md`:

```markdown
# 05 — Quality Gates

> Gates run pre-commit on every task and pre-merge on every phase. Gates that
> fail block the work. No "fix later".

## Per-commit (every task)

- [ ] `uv run pytest -x` — green on touched files' test modules
- [ ] `uv run ruff check .` — clean (or warnings explicitly waived in commit)
- [ ] `uv run ruff format --check .` — formatted
- [ ] No new `print()` calls in `core/` / `src/conexus/`
- [ ] No `# TODO` without a tracking item

## Per-phase (Opus review gate)

- [ ] Full `uv run pytest` — green
- [ ] Eval suite (when Phase 1 lands): `uv run python -m core.evals.runner --gate` — no regression
- [ ] `/simplify` applied to every changed code file (manual review of suggestions OK)
- [ ] `/caveman:compress` applied to every changed prompt file
- [ ] wiki-keeper diff merged
- [ ] Conventional Commits format on every commit
- [ ] Phase plan checklist 100% ticked
- [ ] No `git stash` artefacts; no `WIP` commits in branch history

## Pre-PR

- [ ] Branch rebased on `main`
- [ ] Squash where commits don't add review value (keep TDD red→green pairs)
- [ ] PR description links spec + plan + codex log
- [ ] CI green

## Override discipline

A gate may be overridden only with:

1. One-line justification in the commit message
2. Follow-up task opened in `docs/superpowers/plans/`
3. Operator (Leandro) approval

Three overrides in one phase = stop, retro, fix process.
```

- [ ] **Step 2: Commit**

```bash
git add docs/dev-workflow/05-quality-gates.md
git commit -m "docs(workflow): add per-commit + per-phase quality gates"
```

---

## Task 7: Reference dev-workflow from CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Read current CLAUDE.md**

Run: `head -50 CLAUDE.md`
Goal: locate the section right after "## 4. Goal-Driven Execution" or before "# Conexus — Claude Code Context".

- [ ] **Step 2: Insert dev-workflow reference**

Edit `CLAUDE.md`, after the "These guidelines are working if:" line and before
the `# Conexus — Claude Code Context` header, insert:

```markdown
## 5. Dev Workflow

Implementation work follows `docs/dev-workflow/` — model routing, execution
loop, codex validation, parallel dispatch, quality gates. Read once per
session before touching code.

```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: reference dev-workflow from CLAUDE.md"
```

---

## Task 8: Smoke-run the loop on a trivial change

**Files:**
- Touch: `docs/dev-workflow/README.md` (add a typo, fix it via the loop)

Goal: prove the loop end-to-end works before using it on real Phase 6 work.

- [ ] **Step 1: Introduce a trivial drift**

Edit `docs/dev-workflow/README.md`, add a line "Last revised TODO" at the bottom.

- [ ] **Step 2: Dispatch wiki-keeper**

```
Agent({
  description: "Smoke: detect README TODO",
  subagent_type: "wiki-keeper",
  prompt: "Trigger: docs/dev-workflow/README.md ends with 'Last revised TODO'. Verify and propose fix if drift confirmed. Do not write — propose only."
})
```

Expected: wiki-keeper notes the wiki scope is `docs/wiki/agents-framework/`,
**rejects** the request because target file is outside its scope. This proves
the hard-rule guard works.

- [ ] **Step 3: Restore the file manually**

Run: `git checkout docs/dev-workflow/README.md`

- [ ] **Step 4: Test wiki-keeper on its real scope**

```
Agent({
  description: "Smoke: wiki cross-ref check",
  subagent_type: "wiki-keeper",
  prompt: "Trigger: 2026-04-29-conexus-framework-v2.md spec landed. Should docs/wiki/agents-framework/14-conexus-target-architecture.md cross-reference it? Propose only."
})
```

Expected: subagent reads partition 14 + new spec, returns either "no drift" or
a specific addition with diff.

- [ ] **Step 5: Apply the proposal if reasonable**

Operator decides; if good, accept the diff, commit:

```bash
git add docs/wiki/agents-framework/14-conexus-target-architecture.md
git commit -m "docs(wiki): cross-reference v2 spec from target architecture"
```

If proposal is poor, sharpen the subagent prompt and re-dispatch.

---

## Codex log

(Populate during execution — leave empty until codex runs.)

---

## Self-review

1. **Spec coverage.** Plan covers: model routing (Task 2), execution loop (Task 3), codex validation (Task 4), parallel dispatch (Task 5), quality gates (Task 6), wiki-keeper subagent (Task 1), CLAUDE.md wiring (Task 7), smoke test (Task 8). All ask-bullets from request mapped. ✓
2. **Placeholder scan.** No "TBD", "implement later", "add appropriate". Codex log left intentionally empty as a runtime artefact, labelled as such. ✓
3. **Type consistency.** Subagent name `wiki-keeper` consistent across Tasks 1, 3, 8. File paths consistent. Skill names (`/simplify`, `/caveman:compress`, `codex:rescue`) match installed plugin names. ✓

---

*Last revised 2026-04-29.*
