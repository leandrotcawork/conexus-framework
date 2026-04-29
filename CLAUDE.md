# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## 5. Dev Workflow

Implementation work follows `docs/dev-workflow/` — model routing, execution
loop, codex validation, parallel dispatch, quality gates. Read once per
session before touching code.

# Conexus — Claude Code Context

Personal AI agent framework. Multiple agents (Ana, Pesquisador) share one core runtime and are orchestrated from `main.py`. Runs 24/7 on Fly.io (`gru`), talks over Telegram.

For the full system tour see `docs/SYSTEM.md`. For the agent framework see `docs/ARCHITECTURE.md`.

## Quick start

```bash
uv sync                         # install deps
uv run pytest                   # run the test suite
uv run python main.py           # run both bots + scheduler locally
```

See `docs/ARCHITECTURE.md` for the full framework contract.

## Conventions & gotchas

- **Language:** agent-facing prompts and user replies are pt-BR. Code, comments, and commits are English.
- **Timezone:** always `America/Sao_Paulo` (BRT). `handle_agent_message` appends current BRT time to every system prompt.
- **Tool results must be JSON strings.** `AgentRegistry.execute_tool` serialises them; tool methods return dict/list/str.
- **Don't bypass the registry.** New agent handlers should reuse `handle_agent_message`, not reimplement the tool loop.
- **Idempotency:** scheduled jobs write to `ping_log` before sending and mark after — survives restart. `scheduler.catchup()` runs once on boot.
- **Budget caps are advisory + enforced.** `on_exceed: notify` sends a Telegram message and blocks the reactive call. Jobs ignore the cap by design.
- **SQLite lives on the Fly volume** (`/data/conexus.db`). Wiki markdown lives alongside (`/data/wiki/`, `/data/knowledge/`).
- **Two separate Telegram bots** (Ana + Pesquisador) run in the same process; each has its own token and updater.
- **Pesquisador uses two LLMs:** cheap router (`llm:`) for tool-calling, Gemini Pro (`llm_synthesis:`) for `compile_article`. Keep both in `SKILL.md`.
- **Knowledge wiki is git-backed.** SSH deploy key is injected at startup (`main.py`); don't check it into the repo.
- **Never commit `.env`, `wiki_deploy`, or anything in `/data/`.** `.gitignore` already covers the standard cases.