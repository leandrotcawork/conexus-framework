# System Pulse — Conexus
> Auto-updated: 2026-04-29

## Current Phase
**Phase 7 planned.** SKILL_PACK + TrifectaGuard + BudgetCap — not yet started.
- Phases 0-5 = kernel work; Phase 6 = framework/consumer split (DONE); Phases 7-9 = v2 net-new
- Phase 7 subtasks: 7.1 skills: field → 7.2 SkillLoader → 7.3 backend abstraction → 7.4 TrifectaGuard → 7.5 tag CLI → 7.6 integration tests
- Pre-phase: write implementation plan (`nexus:writing-plans` + spec §1.3, §1.4, §1.8)

## Recent Changes
- 2026-04-29: Phase 6 complete (6 sub-phases, ~15 commits): framework/consumer split, src/conexus/core/, adapters/, CLI entry, dep split, test reorganization, dogfood
- 2026-04-29: Added full dev-workflow infrastructure (9 commits): wiki-keeper subagent, 5 policy docs, CLAUDE.md wiring, wiki partition 14 cross-ref
- (prior sessions not yet recorded)

## Architecture Overview
```
Conexus = Ana + Pesquisador on Fly.io (gru) + Telegram
main.py (shim) → adapters/telegram_runner.py → agents/{ana,pesquisador}/
src/conexus/core/ = framework kernel (agent_handler, agent_registry, llm, memory, scheduler)
src/conexus/cli/ = CLI entry point + build_runtime primitive
adapters/ = consumer wiring (Telegram, SSH, wiki clone)
SQLite @ /data/conexus.db, wiki @ /data/wiki/ (git-backed, SSH key)
Two Telegram bots in one process; APScheduler for jobs
conexus pip wheel = src/conexus/ only (framework deps subset)
```

## Established Patterns
- TDD: write failing test → impl → pass → commit (Conventional Commits)
- Subagent dispatch: fresh Sonnet per task; Opus for phase reviews
- Quality gates: pytest + ruff per-commit; full suite + eval per-phase
- Wiki updates: wiki-keeper subagent after every phase review
- All policy: `docs/dev-workflow/` — read once per session

## Known Risks and Tech Debt
- `codex:codex-rescue` sandbox blocks file reads in this env — direct audit needed for Phase 7 pre-validation
- `src/conexus/cli/__main__.py` imports consumer code (agents.ana.tools, agents.pesquisador.tools) — violates framework purity; fix before Phase 7
- `adapters/telegram_runner.py` still constructs AgentHandlerConfig directly (build_runtime not yet wired in) — duplicate construction path
- `docs/wiki/agents-framework/` commit strategy TBD (local-only vs. tracked)

## Key File Locations
- Kernel loop: `src/conexus/core/agent_handler.py`
- Agent registry: `src/conexus/core/agent_registry.py`
- Framework runtime builder: `src/conexus/cli/runner.py`
- CLI entry point: `src/conexus/cli/__main__.py`
- Consumer wiring: `adapters/telegram_runner.py`
- Boot shim: `main.py`
- Framework tests: `src/conexus/tests/test_framework_*.py`
- Agent tests: `agents/{ana,pesquisador}/tests/`
- Dev workflow: `docs/dev-workflow/` (5 policy docs + README)
- Wiki-keeper subagent: `.claude/agents/wiki-keeper.md`
- V2 spec: `docs/superpowers/specs/2026-04-29-conexus-framework-v2.md`
- Migration plan: `docs/superpowers/plans/2026-04-29-framework-consumer-split-migration.md`

## Active Decisions
- ADR-001: wiki-keeper scope locked to `docs/wiki/agents-framework/` — see `.brain/decisions/001-wiki-keeper-scope.md`
- Monorepo approach for framework/consumer split (per migration plan §2 "Decision: monorepo with two pyproject files first")

## Quality Gates (active)
Per `docs/dev-workflow/05-quality-gates.md`:
- Per-commit: `uv run pytest -x`, `uv run ruff check .`, no print() in core/, no TODO without tracking
- Per-phase: full pytest, Opus review, /simplify, wiki-keeper diff
