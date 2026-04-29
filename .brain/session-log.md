# Last Session — Conexus
> Date: 2026-04-29 | Session: #2

## What Was Accomplished
- Patched migration plan with 4 pre-validation micro-decisions before execution
- Phase 6.1: src/conexus/ stub + pyproject skeletons (framework + agents)
- Phase 6.2: git mv core/ → src/conexus/core/, rewrote ~30 files to conexus.core.*, editable install
- Phase 6.3: Carved main.py → adapters/telegram_runner.py + src/conexus/cli/runner.py; main.py = 12-line shim
- Phase 6.4: Split pyproject deps — framework in [project.dependencies], consumer in [dependency-groups].consumer; wheel builds clean
- Phase 6.5: conexus CLI — `conexus run agent <name>` stdin loop, CONEXUS_AGENTS_DIR env var
- Phase 6.6: Tests reorganized — framework → src/conexus/tests/test_framework_*.py; agents → agents/*/tests/; dogfood 46 passed
- Opus review: APPROVED_WITH_NOTES (74 tests, ruff clean, wheel builds)

## What Changed in the System
- `core/` removed — now at `src/conexus/core/`
- `main.py` is a thin shim; all consumer wiring in `adapters/telegram_runner.py`
- New: `src/conexus/cli/runner.py` (build_runtime framework primitive)
- New: `src/conexus/cli/__main__.py` (conexus CLI entry point)
- New: `adapters/` dir with telegram_runner.py
- pyproject.toml: [project.scripts], [build-system], [dependency-groups].consumer added
- Tests split: 12 framework tests in src/conexus/tests/, 6 agent tests in agents/*/tests/

## Decisions Made This Session
- adapters/ at repo root (not nested) — recorded in migration plan
- APScheduler stays in framework (core scheduler imports it directly)
- CLI agent dir via CONEXUS_AGENTS_DIR env var, default ./agents
- Phase 6.2: editable install immediately after git mv

## What's Immediately Next
- Phase 7 (Skills/Team primitives) — not in roadmap yet; need nexus:nexus-plan
- Before Phase 7: address Opus recommendations:
  1. Wire build_runtime into telegram_runner.py (kills duplicate construction path)
  2. Fix cli/__main__.py hardcoded agent imports (use CONEXUS_AGENTS_DIR discovery)
  3. Run full dogfood: pip install wheel in clean venv + run agents/*/tests/
- Run wiki-keeper (Phase 6 changed framework architecture significantly)

## Open Questions
- When does Phase 7 start? Need planning session to define subtasks
- Should cli/__main__.py move to adapters/ since it imports consumer code? (Opus flagged)
- codex:codex-rescue sandboxed in this env — Phase 7 pre-validation will need direct audit again
