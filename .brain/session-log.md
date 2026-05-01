# Last Session — Conexus
> Date: 2026-04-30 | Session: #4

## What Was Accomplished
- Phase 8 plan written: `docs/superpowers/plans/2026-04-30-phase-8-team-pack.md` (12 tasks, codex pre-phase validated, scope-narrowed)
- T0: AgentRegistry multi-backend (`_backends: dict[str, list[ToolBackend]]`) + `ToolBackend.list_tools()` manifest contract on ABC, Python + Mcp impl
- T1: `Handoff` Pydantic (frozen, schema_version=1, hop_count, max_hops, context_mode, return_on, tags, trust_boundary_cleared) + `handoff_audit` SQLite table
- T2: `TEAM_PACK.md` parser + `TeamLoader` (member exists / share-sum tolerance 0.01 / share keys allowlisted)
- T3: `TeamRegistry` runtime view (members, manager, edges_from, budget, policy)
- T4: `HandoffRouter` — explicit > auto-edge > when-edge > manager fallback
- T5: `BudgetCascader` — pool + per-member shares + 3 policies (notify, halt_member, borrow_from_pool)
- T6: Cross-agent TrifectaGuard — `seed_taint` kwarg + `from_handoff(tool_tags, handoff)`; `incoming_handoff` field on `AgentHandlerConfig`
- T7: `conexus run-team <pack>` CLI subcommand (validate-only; runtime in Phase 9)
- T8: Reference TEAM_PACK at `agents/teams/product_team/` (ana + pm + researcher)
- T9: End-to-end integration test — cross-agent web_fetch (researcher) → wiki_write (pm) blocked + trust-cleared bypass
- T10: Wiki sync via wiki-keeper subagent (partitions 03/05/06/13/14)
- T11: Codex pre-review (changes-needed, 11 blockers) + Opus review (APPROVED_WITH_NOTES)
- B-1 fix: `HandoffRouter._eval` replaced with whitelisted AST walker (eval sandbox escape via `__class__.__bases__[0].__subclasses__()` closed)
- B-3 fix: `HandoffRouter` accepts optional sqlite conn; writes one `handoff_audit` row per route
- B-2/B-4/B-5/B-6/B-7/B-8/B-9/B-10/B-11 explicitly deferred to Phase 9 in plan §"Items Deferred to Phase 9"
- Suite: 52 framework tests passing (Phase 7 + Phase 8 batched); ruff clean on `src/conexus/`

## What Changed in the System
- New: `src/conexus/core/team/` (handoff.py, team_pack.py, team_loader.py, team_registry.py, handoff_router.py, budget_cascader.py)
- New: `src/conexus/core/memory/handoff_audit.py` + wired into `SqliteStore.init_db`
- Modified: `agent_registry.py` — multi-backend dispatch; routes by `ToolBackend.list_tools()`; collision detection
- Modified: `backends/base.py` (+ python + mcp_stdio) — `list_tools()` abstract method on ABC
- Modified: `trifecta/guard.py` — `seed_taint` + `from_handoff` factory
- Modified: `agent_handler.py` — `incoming_handoff: object | None` + 3-branch guard creation
- Modified: `cli/__main__.py` — `run-team <pack>` subcommand
- New: `agents/teams/product_team/{TEAM_PACK.md,__init__.py}`
- New tests: 7 Phase 8 framework test files + extension to `test_framework_backends.py` + new `test_framework_cli.py`

## Decisions Made This Session
- Phase 8 scope narrowed: replay + MCPProducer deferred to Phase 9 (recorded in plan §"Phase 8 Scope Decision")
- HandoffRouter `when:` expressions parsed via AST walker, not eval — TEAM_PACK is pip-installable so author input is untrusted
- Handoff audit captures the *original* envelope (replay fidelity); resolved target reconstructable from edges + outcome
- Phase 9 deferral list explicit: `delegate_to_<agent>` LLM tool, `context_mode` per-edge, `return_on` stack-return, `max_parallel_members`, trust-boundary clear method, pip-install smoke test, `deployment` round-trip, `policy.termination_text` consumed by loop
- Per-task targeted pytest only (not full suite) — Windows full-suite hangs; gates run as batched lists at phase end
- Sequential implementer dispatch (model: sonnet/haiku per task complexity); skipped per-task reviewers after T4 due to Windows test hang; Opus review covered the whole phase at end

## What's Immediately Next
- Push 13 Phase 8 commits + earlier Phase 6/7 commits + wiki commits to remote (deferred per user during prior sessions)
- Optional: re-investigate Windows full-suite pytest hang root cause (likely Telegram-bot or scheduler test that doesn't stop) — out of phase scope
- Phase 9 plan: multi-agent runtime activation (delegate_to_<agent> LLM tool, context_mode/return_on semantics, max_parallel_members, trust-boundary clear, replay, MCPProducer, pip-install smoke)

## Open Questions
- Should `policy.termination_text` default match Claude Code conventions (e.g. "DONE") or be agent-specific? Currently optional in TeamPolicy.
- McpStdioBackend reads single line for tools/list response — vulnerable to interleaved notifications/message log frames; harden in Phase 9.
