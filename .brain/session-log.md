# Last Session — Conexus
> Date: 2026-05-08 | Session: #9

## What Was Accomplished
- Spec written: `docs/superpowers/specs/2026-05-08-memory-and-wiki-architecture-design.md` (7 decisions, Phase split, GitHub App deferred)
- Plan written + codex-validated (2 NO-GO passes fixed, final APPROVE): `docs/superpowers/plans/2026-05-08-memory-and-wiki-phase1.md`
- Task 1: WikiBackend Protocol + safe_join (ea62282)
- Task 2: LocalBackend filesystem impl (ed6cca7)
- Task 3: WikiStore refactored to facade over WikiBackend — git+SSH logic dropped (a3ac340)
- Task 4: SKILL.md schema — `wiki.backend`, `wiki.dir`, `prompt_override`; `IdentitySection.wiki` default=WikiSection() (ecd5037)
- Task 5: IdentityRuntime dispatches on `cfg.wiki.backend` via `_build_wiki()`; stores `skill_dir` (bc0d15b)
- Task 6: `DEFAULT_MEMORY_PROMPT_PT_BR` + `load_memory_prompt()` (dcc6897)
- Task 7: `assemble_identity_context` prepends memory-routing prompt; `agent_handler.py` passes `ir.skill_dir` (19bd10f)
- Task 8: notes-pack `add_note` description warns against identity facts, redirects to `memory_set`/`wiki_write` (a5a1542)
- Task 9: validator SKILL.md gets `identity.wiki: {backend: local}` (0637857)
- Task 10: `.gitignore agents/*/wiki/` (16bb35f)
- Fix: `load_memory_prompt` raises explicit FileNotFoundError for bad `prompt_override` path (a0e5e77)
- Fix: `test_identity_section_minimal` assertion updated for new default-local wiki (61d24d5)
- Opus phase review: SHIP verdict, no blockers
- wiki-keeper: updated 04-memory-systems, 05-skills-prompts, 07-rag-and-wiki (7c5d097)
- 64 Phase 1 tests pass, 1 skipped (Windows symlink), 12 commits

## What Changed in the System
- New package: `src/conexus/core/memory/wiki/` (`__init__`, `backend.py`, `local.py`)
- New module: `src/conexus/core/identity/prompt.py`
- Modified: `wiki_store.py` (191→60 lines, pure facade, no git), `identity_runtime.py` (backend dispatch + skill_dir), `context.py` (prompt prepend + skill_dir param), `agent_handler.py` (passes ir.skill_dir), `skill_loader.py` (backend + prompt_override), `packs/notes/tools.py` (descriptions)
- New tests: `tests/core/memory/wiki/`, `tests/core/identity/test_prompt.py`, `tests/cli/test_identity_runtime_backends.py`, `tests/packs/test_notes_descriptions.py`

## Decisions Made This Session
- WikiBackend Protocol: pluggable backends; Phase 1 = LocalBackend only; Phase 2 = GitHubAppBackend (per-agent repo, GitHub App auth)
- SSH backend dropped entirely — no git in Phase 1 WikiStore
- IdentitySection.wiki defaults to WikiSection() (not None) — backward compat for Anna
- Memory-routing prompt auto-prepended to ALL identity contexts when enabled

## What's Immediately Next
- T-045: Migrate Ana to identity baseline (add `identity:` block to agents/ana/SKILL.md)
- Phase 2 (deferred): GitHub App registration + GitHubAppBackend + OAuth callback in Studio
- Manual E2E REPL test: start Studio, send 3 messages to validator, verify facts/wiki/notes land in right stores

## Open Questions
- Telegram `on_auth_required` factory not wired into actual bot handler yet
- Google Calendar MCP server_url still placeholder
