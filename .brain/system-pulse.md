# System Pulse — Conexus
> Auto-updated: 2026-04-29

## Current Phase
**Workflow infrastructure complete.** Ready for Phase 6 (framework/consumer split).
- Phases 0-5 = kernel work (target arch); Phases 6-9 = v2 net-new
- Workflow loop to use for Phase 6: `docs/dev-workflow/02-execution-loop.md`
- Migration plan: `docs/superpowers/plans/2026-04-29-framework-consumer-split-migration.md`

## Recent Changes
- 2026-04-29: Added full dev-workflow infrastructure (9 commits): wiki-keeper subagent, 5 policy docs, CLAUDE.md wiring, wiki partition 14 cross-ref
- (prior sessions not yet recorded)

## Architecture Overview
```
Conexus = Ana + Pesquisador on Fly.io (gru) + Telegram
main.py → agents/{ana,pesquisador}/ → core/ (kernel)
core/agent_handler.py = single tool-calling loop
core/agent_registry.py = uniform tool dispatch
SQLite @ /data/conexus.db, wiki @ /data/wiki/ (git-backed, SSH key)
Two Telegram bots in one process; APScheduler for jobs
```

## Established Patterns
- TDD: write failing test → impl → pass → commit (Conventional Commits)
- Subagent dispatch: fresh Sonnet per task; Opus for phase reviews
- Quality gates: pytest + ruff per-commit; full suite + eval per-phase
- Wiki updates: wiki-keeper subagent after every phase review
- All policy: `docs/dev-workflow/` — read once per session

## Known Risks and Tech Debt
- `codex:codex-rescue` subagent availability unverified in production (smoke test deferred to Phase 6 kickoff)
- `docs/wiki/agents-framework/` commit strategy TBD (local-only vs. tracked)
- CLAUDE.md was carrying unstaged changes for an unknown period — now committed

## Key File Locations
- Kernel loop: `core/agent_handler.py`
- Agent registry: `core/agent_registry.py`
- Dev workflow: `docs/dev-workflow/` (5 policy docs + README)
- Wiki-keeper subagent: `.claude/agents/wiki-keeper.md`
- V2 spec: `docs/superpowers/specs/2026-04-29-conexus-framework-v2.md`
- Migration plan: `docs/superpowers/plans/2026-04-29-framework-consumer-split-migration.md`
- Target arch wiki: `docs/wiki/agents-framework/14-conexus-target-architecture.md`
- Execution workflow plan: `docs/superpowers/plans/2026-04-29-v2-execution-workflow.md`

## Active Decisions
- ADR-001: wiki-keeper scope locked to `docs/wiki/agents-framework/` — see `.brain/decisions/001-wiki-keeper-scope.md`
- Monorepo approach for framework/consumer split (per migration plan §2 "Decision: monorepo with two pyproject files first")

## Quality Gates (active)
Per `docs/dev-workflow/05-quality-gates.md`:
- Per-commit: `uv run pytest -x`, `uv run ruff check .`, no print() in core/, no TODO without tracking
- Per-phase: full pytest, Opus review, /simplify, wiki-keeper diff
