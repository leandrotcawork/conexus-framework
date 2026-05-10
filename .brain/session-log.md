# Last Session — Conexus
> Date: 2026-05-09 | Session: #11

## What Was Accomplished
- Codex pre-validated Phase 2 plan (3 rounds: 3 blockers fixed then APPROVE)
- Dispatched T1+T2 in parallel (JWT auth + DB schema)
- Dispatched T3+T4 in parallel (GitHubAppBackend + OAuth callback route)
- Dispatched T5+T6 in parallel (identity_runtime wire + Studio UI)
- Fixed 2 bugs found during T3 execution: README seeding removed from _ensure_clone, delete() reordered to pull-before-check
- Opus review: SHIP — applied post-review fix (delete() order + test mock scope)
- wiki-keeper updated 4 partitions (00-index, 04-memory, 07-rag-wiki, 21-studio)
- Phase 2 complete: 7 commits, 24 tests green, ruff clean

## What Changed in the System
- New: `src/conexus/core/memory/wiki/git_auth.py` — JWT + installation token cache
- New: `src/conexus/core/memory/wiki/github_app.py` — GitHubAppBackend (WikiBackend impl)
- New: `src/conexus/web/admin/routes/github_wiki.py` — OAuth install callback routes
- Modified: `src/conexus/core/memory/wiki/__init__.py` — exports GitHubAppBackend
- Modified: `src/conexus/core/memory/sqlite_store.py` — github_app_installs table + 3 helpers
- Modified: `src/conexus/cli/identity_runtime.py` — _build_wiki signature + github_app branch
- Modified: `src/conexus/web/admin/routes/agents.py` — github_install context + disconnect endpoint
- Modified: `src/conexus/web/admin/templates/agents/edit.html` — Connect/Disconnect section

## Decisions Made This Session
- gh: prefix isolation in oauth_pkce_state.code_verifier (reuses Phase 11 table safely)
- delete() pulls before checking existence (remote-only files are deletable after pull)
- local_root=skill_dir/"wiki" for GitHubAppBackend (Fly.io volume concern deferred)

## What's Immediately Next
- Phase 10 is now complete (all tasks done including T-063 Phase1 + Phase2 implied by T-063 notes)
- T-045 (Ana identity migration) was permanently skipped by user
- No active phase — user to decide next priority

## Open Questions
- Fly.io: local_root=skill_dir/"wiki" may need to move to data_dir for volume persistence
- git subprocess blocks event loop — asyncio.to_thread deferred to future phase
- Telegram on_auth_required factory still not wired into actual bot handler
