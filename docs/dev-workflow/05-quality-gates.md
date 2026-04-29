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
