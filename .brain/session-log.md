# Last Session — Conexus
> Date: 2026-04-29 | Session: #1

## What Was Accomplished
- Created `.claude/agents/wiki-keeper.md` — custom subagent for docs drift detection (scope: docs/wiki/agents-framework/)
- Created `docs/dev-workflow/` with 5 policy docs: model routing, execution loop, codex validation, parallel dispatch, quality gates
- Added `## 5. Dev Workflow` reference section to `CLAUDE.md`
- Fixed `.gitignore` to allow tracking `.claude/agents/` while blocking rest of `.claude/`
- Smoke-tested wiki-keeper: scope-guard confirmed (refused out-of-scope write), real-scope test produced accurate v2 spec cross-ref
- Updated `docs/wiki/agents-framework/14-conexus-target-architecture.md` with v2 spec cross-reference and Phase 0-5 scope qualifier
- Opus end-of-plan review: APPROVED (no blocking issues)

## What Changed in the System
- New dir: `.claude/agents/` (now tracked in git via `!.claude/agents/` negation in .gitignore)
- New dir: `docs/dev-workflow/` with 6 files (README + 5 policy docs)
- CLAUDE.md behavioral guidelines now in git (was unstaged); section 5 added
- `docs/wiki/agents-framework/14-conexus-target-architecture.md` now tracked in git (first commit)

## Decisions Made This Session
- Use monorepo `.claude/agents/` for custom subagents (vs. separate plugin install)
- wiki-keeper scope locked to `docs/wiki/agents-framework/` only — keeps blast radius minimal
- `docs/wiki/agents-framework/` must remain unignored so wiki-keeper's `git diff` output works

## What's Immediately Next
- Phase 6 of Conexus target architecture: framework/consumer split
  - Phase 6.1: repo prep (pyproject skeletons, src/conexus/ dir stub)
  - Run codex pre-validation on `docs/superpowers/plans/2026-04-29-framework-consumer-split-migration.md` first
  - Reference: `docs/dev-workflow/02-execution-loop.md` for the full loop to follow

## Open Questions
- Is `codex:codex-rescue` available as a subagent_type in this environment? (Verified yes in this session, but first real pre-phase validation will confirm)
- Should `docs/wiki/agents-framework/` files be committed going forward or kept local-only?
