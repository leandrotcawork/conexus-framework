# System Pulse — Conexus
> Auto-updated: 2026-05-01

## Current Phase
**ALL PHASES COMPLETE.** Phase 9 shipped: multi-agent runtime (handle_team_message), delegate_to_<agent> LLM tool, context_mode/return_on, replay, MCPProducer, tool_audit, hop chaining, cross-agent Trifecta taint propagation. 87 new tests. All 5 phases done.

## Recent Changes
- 2026-05-01: Phase 9 complete (~12 commits). Stack-based team loop in agent_handler.py; delegate_tool.py + transcript.py; replay.py + tool_audit.py; mcp/producer.py (FastMCP); McpStdioBackend hardened (Lock + id correlation); CLI: mcp-server + replay subcommands. 87 new tests passing.
- 2026-04-30: Phase 8 complete (15 commits d476101..b7fa52c). Codex pre-review found 11 blockers; B-1 (router AST sandbox escape) + B-3 (audit not wired) fixed inline at aa717aa; remaining 9 deferred to Phase 9 with rationale. Opus review APPROVED_WITH_NOTES; cosmetic fixes applied (b7fa52c).
- 2026-04-30: Phase 7 follow-up fixes (16f864f): SkillLoader.start_all/stop_all lifecycle for mcp-stdio; class detection tightened (v.__module__ == mod.__name__).
- 2026-04-30: Wiki sync (45eff1a): Phase 8 partitions 03/05/06/13/14 updated; partition 06 now has full §13 multi-agent orchestration section.
- 2026-04-30: Phase 7 complete (8 tasks): SKILL_PACK, DataClass/auto_tag, TrifectaGuard, ToolBackend/PythonBackend, McpStdioBackend, SkillLoader, handler hook, tag CLI.
- 2026-04-29: Phase 6 complete (6 sub-phases, ~15 commits): framework/consumer split, src/conexus/core/, adapters/, CLI entry, dep split, dogfood.

## Architecture Overview
```
Conexus = Ana + Pesquisador on Fly.io (gru) + Telegram
main.py (shim) → adapters/telegram_runner.py → agents/{ana,pesquisador}/
src/conexus/core/ = framework kernel (agent_handler, agent_registry, llm, memory, scheduler)
  + skills/ (pack_loader, skill_resolver) + trifecta/ (tags, guard) + backends/ (base, python, mcp_stdio)
  + team/ (handoff, team_pack, team_loader, team_registry, handoff_router, budget_cascader,    ← Phase 8
           delegate_tool, transcript, replay)                                                   ← Phase 9
  + memory/handoff_audit.py, tool_audit.py                                                     ← Phase 8/9
  + mcp/__init__.py, mcp/producer.py (FastMCP wiki server)                                     ← Phase 9
src/conexus/cli/ = CLI entry point + build_runtime + tag suggest + run-team + mcp-server + replay
adapters/ = consumer wiring (Telegram, SSH, wiki clone)
agents/teams/product_team/TEAM_PACK.md = reference 3-member pack (ana + pm + researcher)
SQLite @ /data/conexus.db (now includes handoff_audit table), wiki @ /data/wiki/
Two Telegram bots in one process; APScheduler for jobs
conexus pip wheel = src/conexus/ only (framework deps subset)
```

## Established Patterns
- TDD: write failing test → impl → pass → commit (Conventional Commits)
- Subagent dispatch: fresh Sonnet/Haiku per task (sequential — file conflicts); Opus for phase reviews
- Quality gates: pytest + ruff per-commit; **batched targeted tests at phase end** (Windows full-suite hangs)
- Wiki updates: wiki-keeper subagent after every phase review
- Codex pre-review: mandatory per `docs/dev-workflow/03-codex-validation.md`; verdict logged in plan §"Codex log"
- All policy: `docs/dev-workflow/` — read once per session

## Known Risks and Tech Debt
- `codex:codex-rescue` sandbox blocks file reads in this env — direct audit needed for future phases
- Windows pytest full suite hangs (>2 min, no output) — likely scheduler/Telegram test that doesn't stop; bypass via per-file batched runs
- Phase 6/7/8/9/wiki commits all local; not pushed to remote yet (deferred per user)
- Pre-existing ruff F401 in scripts/bootstrap_google.py + tests/conftest.py (unused imports) — pre-Phase-7 tech debt, untouched per surgical-changes policy
- SqliteStore.conn property returns unclosed connection — callers responsible for closing (test/audit pattern only)
- MCPProducer bearer_token in env var only; no rotation/refresh mechanism yet

## Key File Locations
- Kernel loop: `src/conexus/core/agent_handler.py`
- Agent registry: `src/conexus/core/agent_registry.py` (multi-backend, routes via list_tools())
- Backend ABC: `src/conexus/core/backends/base.py` (incl. list_tools() contract)
- SKILL_PACK parser: `src/conexus/core/skills/pack_loader.py`
- SkillLoader: `src/conexus/core/skills/skill_resolver.py`
- TrifectaGuard: `src/conexus/core/trifecta/guard.py` (incl. seed_taint + from_handoff)
- DataClass/auto_tag: `src/conexus/core/trifecta/tags.py`
- Handoff envelope: `src/conexus/core/team/handoff.py`
- HandoffRouter: `src/conexus/core/team/handoff_router.py` (AST walker; audit-aware)
- TeamLoader/Registry: `src/conexus/core/team/{team_loader,team_registry,team_pack}.py`
- BudgetCascader: `src/conexus/core/team/budget_cascader.py`
- Audit tables: `src/conexus/core/memory/handoff_audit.py`, `tool_audit.py`
- Replay runner: `src/conexus/core/team/replay.py`
- MCP producer: `src/conexus/core/mcp/producer.py`
- Delegate tool: `src/conexus/core/team/delegate_tool.py`
- Transcript trim: `src/conexus/core/team/transcript.py`
- Reference team: `agents/teams/product_team/TEAM_PACK.md`
- Framework runtime builder: `src/conexus/cli/runner.py`
- CLI entry point: `src/conexus/cli/__main__.py` (run agent / tag / run-team / mcp-server / replay)
- Consumer wiring: `adapters/telegram_runner.py`
- Boot shim: `main.py`
- Framework tests: `src/conexus/tests/test_framework_*.py`
- Dev workflow: `docs/dev-workflow/`
- Phase 9 plan: `docs/superpowers/plans/2026-04-30-phase-9-runtime-replay-mcp.md`

## Active Decisions
- ADR-001: wiki-keeper scope locked to `docs/wiki/agents-framework/`
- Monorepo approach for framework/consumer split (per migration plan §2)
- HandoffRouter `when:` expressions evaluated via whitelisted AST walker — `eval` is unsafe for pip-installed third-party TEAM_PACKs (B-1 fix at aa717aa)
- Handoff audit captures original envelope (replay fidelity); resolved target reconstructable from edges + outcome string
- Phase 9: serial-only delegation enforced via `break` after first delegation per LLM turn; max_parallel_members validated but not truly parallel yet
- Phase 9: `SqliteStore.conn` is a property (new connection each call, unclosed); long-lived writes use explicit `sqlite3.connect` in handle_team_message
- Phase 9: FastMCP template resources surface in `list_resource_templates()`, not `list_resources()`

## Quality Gates (active)
Per `docs/dev-workflow/05-quality-gates.md`:
- Per-commit: targeted `uv run pytest -k` or per-file path, `uv run ruff check .`, no print() in core/, no TODO without tracking
- Per-phase: batched framework test list (full suite hangs on Windows), Opus review, /simplify, wiki-keeper diff, codex pre-review
