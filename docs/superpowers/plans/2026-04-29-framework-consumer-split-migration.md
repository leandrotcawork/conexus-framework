# Migration Plan — Framework / Consumer Split (2026-04-29)

> **Companion to:** `docs/superpowers/specs/2026-04-29-conexus-framework-v2.md` Phase 6.
> **Goal:** Separate Conexus *framework* (kernel + skill/team primitives + MCP) from *consumer* code (Ana, Pesquisador, future agents) without breaking production.
> **Posture:** Incremental, refactor-only. No behavior change per step. Each step ends green: `uv run pytest` passes + Fly deploy clean.

## 0. Why now

Today's repo mixes runtime + agents:

```
core/          # framework (kernel, registries, budget, LLM, memory)
agents/        # consumer (Ana, Pesquisador SKILL.md + tools)
main.py        # boot: hardcodes Ana + Pesquisador, Telegram tokens, wiki paths
pyproject.toml # one package, one set of deps
```

External consumer (any future user) cannot install Conexus without inheriting
Ana's persona, Pesquisador's wiki, the Telegram boot path. v2 spec §1.1 requires
clean split.

## 1. Target layout

```
conexus-framework/                      # repo A (or sub-pkg of monorepo)
├── pyproject.toml                      # package: conexus
├── src/conexus/
│   ├── core/                           # ← today's core/ verbatim
│   ├── skills/                         # NEW (v2 Phase 7)
│   ├── team/                           # NEW (v2 Phase 8)
│   ├── mcp/                            # NEW (v2 Phase 9)
│   └── cli/
│       └── __main__.py                 # `python -m conexus run agent <x>`
├── tests/                              # framework-only tests
└── README.md

conexus-agents/                         # repo B (or sibling sub-pkg)
├── pyproject.toml                      # depends on conexus
├── agents/
│   ├── ana/  SKILL.md  tools.py  jobs.py
│   └── pesquisador/  SKILL.md  tools.py  jobs.py
├── adapters/                           # DECISION: lives at repo root (./adapters/), not nested
│   └── telegram_runner.py              # ← today's main.py minus framework wiring
├── deploy/
│   ├── fly.toml
│   ├── Dockerfile
│   └── .env.example
└── tests/                              # agent-specific tests
```

**Decision: monorepo with two pyproject files first, split repos only if pain shows up.**
Reasons: shared CI, atomic refactors during Phase 6, single PR review surface.
Repo split is reversible later; premature split is not.

## 2. Phasing

### Phase 6.1 — Repo prep (0.5 day)

- Add `pyproject-framework.toml` skeleton at repo root (placeholder, not active yet).
- Add `pyproject-agents.toml` skeleton.
- Create `src/conexus/` directory (empty); leave existing `core/` in place.
- Add CI lane `framework-tests` that runs only `tests/test_framework_*.py` (empty for now).

**Gate:** existing `uv run pytest` still green. No package layout change yet.

### Phase 6.2 — Move `core/` → `src/conexus/core/` (1 day)

Single mechanical refactor. Three commits:

1. `git mv core/ src/conexus/core/` + add `src/conexus/__init__.py`.
2. Run `uv pip install -e .` immediately after move so imports resolve during step 3.
3. Find/replace imports: `from core.` → `from conexus.core.`. ~30 files.
4. Update `pyproject.toml` `[tool.uv.sources]` / package dirs.

**Gate:**
- `uv run pytest` green.
- `python -c "from conexus.core.agent_registry import AgentRegistry"` works.
- Local `python main.py` boots both bots.

**Risk:** circular imports if any `core` module imports from `agents`. Audit
before move. Spot check: `grep -r "from agents" core/` should return zero.

### Phase 6.3 — Move agent code out of `main.py` (1 day)

Today `main.py` does:
- env load + SSH key install (deploy concern)
- store + wiki + LLM build (framework concern)
- agent registry + tool wiring (consumer concern)
- Telegram bot start (consumer concern)
- scheduler boot + jobs (mixed)

Split into:

```
src/conexus/cli/runner.py               # framework: build_runtime(skill_path) → AgentRuntime
adapters/telegram_runner.py             # consumer: env load + SSH + per-agent wire + bot start
adapters/scheduler_runner.py            # consumer: schedule jobs from agent jobs.py
```

`main.py` becomes a thin shim:

```python
from adapters.telegram_runner import run
import asyncio
asyncio.run(run(["ana", "pesquisador"]))
```

**Gate:**
- `uv run python main.py` boots identical to before.
- Telegram messages route to correct agent; scheduler fires same jobs.
- Smoke: send "oi" to Ana, get same reply shape as pre-migration.

### Phase 6.4 — Carve framework `pyproject.toml` (1 day)

Split deps:

| Stays in framework            | Moves to consumer                       |
|-------------------------------|-----------------------------------------|
| `litellm`, `tenacity`         | `python-telegram-bot`                   |
| `pydantic`, `aiohttp`         | `google-api-python-client` (Ana tool)   |
| `mcp`, `fastmcp` (Phase 9)    | `youtube-transcript-api` (Pesq tool)    |
| `rank-bm25` (memory)          | agent-specific HTTP libs                |
| `apscheduler` (DECISION: stays in framework — `core/agent_handler.py` imports it directly) | |

Audit each dep with `uv tree` + grep for actual import sites. Move only what
agents import directly.

`pyproject-framework.toml` activates → renamed to `pyproject.toml` at framework
root. Consumer pyproject sits at repo root + sub-path.

**Gate:**
- `uv build` produces `conexus-0.1.0-*.whl`.
- Local `pip install dist/conexus-*.whl` into fresh venv → `python -c "import conexus"` works.
- Consumer side: `uv sync --no-dev` then `uv run python main.py` boots.

### Phase 6.5 — `conexus` CLI entry (0.5 day)

```
conexus run agent <name>            # solo
conexus run team <name>             # team (Phase 8)
conexus tag --suggest <tools.py>    # auto-tag heuristic preview (Phase 7)
conexus init <agent_name>           # scaffold new agent (post-Phase 7)
```

Phase 6.5 ships only `conexus run agent <name>`. Reads `agents/<name>/SKILL.md`,
builds runtime, blocks on stdin loop or adapter-bound entry.

**DECISION:** Agent directory resolved via env var `CONEXUS_AGENTS_DIR` (default `./agents`).
No hardcoded path. Allows consumers to place agents anywhere.

**Gate:** `conexus run agent ana` from CLI does what `python main.py`
single-bot mode does.

### Phase 6.6 — Tag tests + dogfood (0.5 day)

Mark every existing test:

- `tests/test_framework_*.py` → moves under `src/conexus/tests/`
- `tests/test_agent_*.py` → stays under `agents/<x>/tests/`
- Shared fixtures (`conftest.py`) → split or duplicate

Dogfood: build framework wheel, install in fresh venv, run consumer tests
against it. Catches API leaks (consumer reaching into framework internals).

**Gate:** consumer test suite passes against `pip install conexus` (not editable).

## 3. Backward compat strategy

**None on internal APIs.** Framework is pre-1.0; consumers (only us) update in
lockstep. No deprecation shims, no `__all__` ceremony.

**Yes on user-visible surface:**
- Telegram tokens, env vars, SQLite schema, wiki paths — unchanged.
- Existing chat history, ping_log, llm_usage rows — unchanged.
- SKILL.md frontmatter — unchanged in Phase 6 (extends in Phase 7 with `skills:` list).

## 4. Rollback

Each phase is one PR. Rollback = `git revert <PR>`. Phases 6.1-6.6 leave no DB
migrations, no destructive ops. Worst case: revert and re-plan.

Phase 6.4 has the most risk (dep split). Mitigation: do not delete deps from
the framework `pyproject.toml` until consumer pyproject is proven to install
clean. Window of duplication is acceptable.

## 5. Validation per phase

Run after each phase, in order:

```
1. uv run pytest                                  # all green
2. uv run python -c "import conexus.core.agent_registry"  # framework imports
3. uv run python main.py                          # boots both bots locally
4. send "ping" to @AnaBot                         # reactive turn works
5. wait for next scheduled briefing               # scheduler works
6. check /data/wiki git log                       # wiki write path intact
```

Phase 6.4 adds:

```
7. uv build && uv pip install dist/*.whl          # wheel installable
8. python -c "from conexus.cli import runner"     # public surface intact
```

## 6. Deferred (not Phase 6)

- Splitting `conexus-agents` into its own repo — wait until external user wants Conexus standalone.
- Publishing `conexus` to PyPI — wait until Phase 9 ships (real surface to depend on).
- Migrating Ana / Pesquisador SKILL.md to new `skills:` list format — Phase 7 work.
- Per-agent wiki repo separation — already partially in place via env vars; clean up in Phase 7.

## 7. Effort + sequencing

| Sub-phase | What                                          | Days |
|-----------|-----------------------------------------------|------|
| 6.1       | Repo prep, empty skeletons                    | 0.5  |
| 6.2       | Move `core/` → `src/conexus/core/`            | 1    |
| 6.3       | Carve agent code out of `main.py`             | 1    |
| 6.4       | Split `pyproject.toml`                        | 1    |
| 6.5       | `conexus` CLI entry                           | 0.5  |
| 6.6       | Tag tests, dogfood install                    | 0.5  |
| **Total** |                                               | **4.5** |

Sequence is strict — each phase depends on previous. Single operator can run
this in one focused week.

## 8. Open questions

1. **Monorepo or split repos.** Plan defaults to monorepo. Revisit after Phase 6.6 if PR review surface is painful.
2. **Adapters layout.** DECIDED: `adapters/` lives at repo root (`./adapters/`). Promote to sub-pkg only if a third adapter (REST, voice) lands.
3. **Per-agent venv.** Currently one venv for both bots + framework. Acceptable while consumers + framework co-version. Split when external consumer ships.
4. **CI matrix.** After Phase 6.4, framework tests should run against multiple Python versions (3.11, 3.12). Consumer stays pinned to deploy version.

---

*Migration spec is load-bearing. Implementation that contradicts must update this doc first or be rejected. Last revised 2026-04-29 (pre-validation patch: adapters/ at root, APScheduler stays framework, CONEXUS_AGENTS_DIR, editable install in 6.2).*
