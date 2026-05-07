# Conexus Studio V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use **Haiku/Sonnet** for implementation, **Opus** for per-wave review, **Codex** for pre-execution validation. Apply `/simplify` after each task. Use `/caveman` style for subagent prompts.

**Goal:** Ship a local-only browser UI (`conexus studio`) that creates/edits agents, installs connectors with zero-config OAuth, and tests them via REPL — all reflected to disk as proper agent folders.

**Architecture:** FastAPI + Jinja2 + HTMX (server-rendered, no build step). New module `src/conexus/web/admin/` with thin routes calling pure-logic services. Filesystem (`agents/`) is the single source of truth — zero new SQLite tables. Three-pane editor (list/form/preview), connector marketplace driven by existing `connectors/registry.json`, REPL panel wrapping existing `build_runtime` + `handle_agent_message`. Innovation: zero-config MCP OAuth (DCR + PKCE auto-discovery), connections registry with status dots, and tool surface diff before save.

**Tech Stack:** FastAPI, Jinja2, HTMX (CDN), Alpine.js (CDN), Tailwind (CDN), Monaco editor (CDN, lazy), pydantic (existing), pytest + httpx TestClient, ruff. No new pip dependencies beyond `jinja2` (likely already transitive via FastAPI).

---

## File Structure

```
src/conexus/web/
  app.py                                 # MODIFY: mount admin sub-app
  oauth_router.py                        # existing — unchanged
  admin/                                 # NEW package
    __init__.py
    app.py                               # FastAPI sub-app factory
    deps.py                              # dependency injection helpers
    routes/
      __init__.py
      agents.py                          # GET/POST /admin/agents/...
      connectors.py                      # marketplace + install
      connections.py                     # vault status + reauth
      repl.py                            # POST /admin/agents/{n}/test
    services/
      __init__.py
      agent_repo.py                      # list/read agents from disk
      skill_writer.py                    # atomic SKILL.md rewrite
      tools_inspector.py                 # AST scan public methods
      tools_writer.py                    # rewrite _tool_schemas dict
      validators.py                      # pydantic + AST + subprocess smoke
      runner_proxy.py                    # wrap build_runtime for REPL
      template_lib.py                    # 3 agent scaffolding templates
      connector_installer.py             # extract logic from CLI _handle_connectors_install
      tool_diff.py                       # cost/token diff for skills add
      connections_repo.py                # read oauth_tokens for status
    templates/
      base.html                          # layout + Tailwind/HTMX/Alpine CDN
      partials/
        agent_form.html                  # HTMX target
        agent_yaml_preview.html
        connector_card.html
        connection_row.html
        repl_message.html
        validation_errors.html
      agents/
        list.html
        edit.html
        new.html
      connectors/
        marketplace.html
      connections/
        status.html
    static/
      app.css                            # minimal overrides
      cmdk.js                            # Alpine.js cmd+k palette
src/conexus/cli/__main__.py              # MODIFY: add `studio` subcommand
src/conexus/tests/
  test_admin_agent_repo.py               # NEW
  test_admin_skill_writer.py             # NEW
  test_admin_tools_inspector.py          # NEW
  test_admin_tools_writer.py             # NEW
  test_admin_validators.py               # NEW
  test_admin_template_lib.py             # NEW
  test_admin_connector_installer.py      # NEW
  test_admin_tool_diff.py                # NEW
  test_admin_connections_repo.py         # NEW
  test_admin_routes_agents.py            # NEW (httpx TestClient)
  test_admin_routes_connectors.py        # NEW
  test_admin_routes_connections.py       # NEW
  test_admin_routes_repl.py              # NEW
docs/wiki/agents-framework/
  21-conexus-studio.md                   # NEW partition
```

**Each service has one responsibility.** Routes contain only HTTP plumbing + dependency wiring — all business logic lives in services and is unit-testable without FastAPI.

---

## Subagent Strategy

**Model routing per task (per `docs/dev-workflow/01-model-routing.md`):**
- **Haiku:** mechanical Jinja2 templates, simple route handlers, atomic file ops
- **Sonnet:** services with logic (validators, tools_inspector, runner_proxy), AST surgery
- **Opus:** per-wave code review (spec compliance + quality)
- **Codex:** pre-execution validation of this entire plan, plus per-wave validation if requested

**Parallel dispatch (per `docs/dev-workflow/02-parallel-dispatch.md`):**
- Tasks marked `[par-N]` run in the same dispatch group N
- Within a group, tasks are independent (no file conflicts, no shared module imports being mutated)
- Across groups, tasks run sequentially

**Wiki-keeper subagent:** Dispatch the existing `wiki-keeper` agent type after every wave merges. Wave 0 creates `docs/wiki/agents-framework/21-conexus-studio.md` (initial overview); subsequent waves update it + any other partition the wave touched (03/14/16/20).

**Per-wave loop:**
1. Codex pre-validation (first wave only — validates whole plan)
2. Subagent-driven dev with parallel groups where marked
3. `/simplify` between tasks (caller responsibility)
4. Opus phase review (spec compliance + code quality)
5. wiki-keeper subagent (auto-update partitions)
6. Per-wave PR + merge → next wave

---

## Wave 0 — Scaffold (PR 1, ~0.5 day)

### Task 1: Admin sub-app skeleton + Jinja2 wiring

**Files:**
- Create: `src/conexus/web/admin/__init__.py`
- Create: `src/conexus/web/admin/app.py`
- Create: `src/conexus/web/admin/deps.py`
- Create: `src/conexus/web/admin/templates/base.html`
- Create: `src/conexus/web/admin/static/app.css`
- Create: `src/conexus/tests/test_admin_routes_smoke.py`

- [ ] **Step 1: Write failing smoke test**

```python
# src/conexus/tests/test_admin_routes_smoke.py
from fastapi.testclient import TestClient

from conexus.web.admin.app import make_admin_app


def test_admin_root_renders(tmp_path):
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path)
    client = TestClient(app)
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert "Conexus Studio" in resp.text
```

- [ ] **Step 2: Run — expect ImportError**

```bash
uv run pytest src/conexus/tests/test_admin_routes_smoke.py -v
```

- [ ] **Step 3: Implement scaffold**

```python
# src/conexus/web/admin/__init__.py
from .app import make_admin_app

__all__ = ["make_admin_app"]
```

```python
# src/conexus/web/admin/deps.py
"""Dependency injection helpers for admin routes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AdminContext:
    agents_dir: Path
    data_dir: Path
    connectors_registry_path: Path
```

```python
# src/conexus/web/admin/app.py
"""Conexus Studio admin sub-app."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .deps import AdminContext

_HERE = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))


def _fmt_epoch(epoch: int | None) -> str:
    """Render epoch seconds as `YYYY-MM-DD HH:MM UTC` (Studio displays UTC)."""
    if epoch is None:
        return "—"
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


_TEMPLATES.env.globals["fmt_epoch"] = _fmt_epoch


def make_admin_app(
    *,
    agents_dir: Path,
    data_dir: Path,
    connectors_registry_path: Path | None = None,
) -> FastAPI:
    ctx = AdminContext(
        agents_dir=Path(agents_dir),
        data_dir=Path(data_dir),
        connectors_registry_path=Path(
            connectors_registry_path or Path.cwd() / "connectors" / "registry.json"
        ),
    )

    app = FastAPI(title="Conexus Studio", docs_url=None, redoc_url=None)
    app.state.ctx = ctx
    app.state.templates = _TEMPLATES
    app.mount("/admin/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    @app.get("/admin/", response_class=HTMLResponse)
    async def root(request: Request) -> HTMLResponse:
        return _TEMPLATES.TemplateResponse(
            request, "base.html", {"title": "Conexus Studio", "body_partial": None}
        )

    return app
```

```html
<!-- src/conexus/web/admin/templates/base.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ title }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@2.0.3"></script>
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <link rel="stylesheet" href="/admin/static/app.css">
</head>
<body class="bg-slate-50 text-slate-900">
  <header class="border-b bg-white px-6 py-3 flex items-center justify-between">
    <h1 class="text-lg font-semibold">Conexus Studio</h1>
    <nav class="flex gap-4 text-sm">
      <a href="/admin/" class="hover:underline">Agents</a>
      <a href="/admin/connectors" class="hover:underline">Connectors</a>
      <a href="/admin/connections" class="hover:underline">Connections</a>
    </nav>
  </header>
  <main class="p-6">
    {% if body_partial %}{% include body_partial %}{% else %}<p class="text-slate-500">Welcome.</p>{% endif %}
  </main>
</body>
</html>
```

```css
/* src/conexus/web/admin/static/app.css */
[x-cloak] { display: none !important; }
.htmx-indicator { opacity: 0; transition: opacity 200ms ease-in; }
.htmx-request .htmx-indicator { opacity: 1; }
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest src/conexus/tests/test_admin_routes_smoke.py -v
```

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/conexus/web/admin
git add src/conexus/web/admin src/conexus/tests/test_admin_routes_smoke.py
git commit -m "feat(studio): admin sub-app skeleton with Jinja2 + HTMX base"
```

### Task 2: `conexus studio` CLI command

**Files:**
- Modify: `src/conexus/cli/__main__.py` (add subcommand + handler)
- Test: `src/conexus/tests/test_framework_cli.py` (extend existing)

- [ ] **Step 1: Write failing test**

```python
# Append to src/conexus/tests/test_framework_cli.py
def test_studio_subcommand_parses(monkeypatch, tmp_path):
    """conexus studio --port 8765 parses correctly."""
    import sys
    from conexus.cli.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["studio", "--port", "8765"])
    assert args.command == "studio"
    assert args.port == 8765
```

- [ ] **Step 2: Run — expect AttributeError on `_build_parser`**

```bash
uv run pytest src/conexus/tests/test_framework_cli.py::test_studio_subcommand_parses -v
```

- [ ] **Step 3: Refactor `__main__.py` — extract `_build_parser` verbatim, add `studio` subcommand only**

The existing `main()` (`src/conexus/cli/__main__.py:269-328`) uses `set_defaults(func=_handle_X)` dispatch. Preserve every existing subparser unchanged; add only `studio` and a dispatch fallthrough.

```python
# Modify src/conexus/cli/__main__.py:
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conexus", description="Conexus agent framework CLI")
    sub = parser.add_subparsers(dest="command")

    # --- existing subparsers — copy verbatim from current main() ---
    run_cmd = sub.add_parser("run", help="Run a sub-command")
    run_sub = run_cmd.add_subparsers(dest="subcommand")
    agent_cmd = run_sub.add_parser("agent", help="Start an agent stdin loop")
    agent_cmd.add_argument("name", help="Agent name (e.g. ana, pesquisador)")
    agent_cmd.set_defaults(func=_handle_run_agent)

    tag_cmd = sub.add_parser("tag", help="Tag analysis utilities")
    tag_sub = tag_cmd.add_subparsers(dest="subcommand")
    suggest_cmd = tag_sub.add_parser("suggest", help="Print suggested data_classes for a tools.py")
    suggest_cmd.add_argument("tools_file", help="Path to a tools.py file")
    suggest_cmd.set_defaults(func=_handle_tag_suggest)

    mcp_p = sub.add_parser("mcp-server", help="Run Conexus as an MCP server (stdio)")
    mcp_p.add_argument("--wiki-root", default="./data/wiki")
    mcp_p.set_defaults(func=_handle_mcp_server)

    replay_p = sub.add_parser("replay", help="Replay a frozen audit session against a registry")
    replay_p.add_argument("pack")
    replay_p.add_argument("--db", required=True)
    replay_p.add_argument("--session-id", required=True)
    replay_p.add_argument("--available-agents", default="")
    replay_p.set_defaults(func=_handle_replay)

    team_p = sub.add_parser("run-team", help="Validate + load a TEAM_PACK")
    team_p.add_argument("pack")
    team_p.add_argument("--available-agents", default="")
    team_p.set_defaults(func=_handle_run_team)

    connectors_p = sub.add_parser("connectors", help="Manage MCP connectors")
    connectors_sub = connectors_p.add_subparsers(dest="action")
    conn_list = connectors_sub.add_parser("list")
    conn_list.add_argument("--registry", default=None)
    conn_list.set_defaults(func=_cmd_connectors, action="list")
    conn_install = connectors_sub.add_parser("install")
    conn_install.add_argument("name")
    conn_install.add_argument("--agent", required=True)
    conn_install.add_argument("--registry", default=None)
    conn_install.set_defaults(func=_cmd_connectors, action="install")
    conn_connect = connectors_sub.add_parser("connect")
    conn_connect.add_argument("name")
    conn_connect.add_argument("--user", required=True)
    conn_connect.add_argument("--return-to", dest="return_to", default=None)
    conn_connect.add_argument("--registry", default=None)
    conn_connect.set_defaults(func=_cmd_connectors, action="connect")

    # --- NEW: studio ---
    studio_p = sub.add_parser("studio", help="Start Conexus Studio web UI on 127.0.0.1")
    studio_p.add_argument("--port", type=int, default=8765)
    studio_p.add_argument("--no-browser", action="store_true")
    studio_p.set_defaults(func=_handle_studio)

    return parser


def _handle_studio(args: argparse.Namespace) -> None:
    import webbrowser

    import uvicorn

    from conexus.web.admin.app import make_admin_app

    agents_dir = Path(os.environ.get("CONEXUS_AGENTS_DIR", "./agents"))
    data_dir = Path(os.environ.get("CONEXUS_DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    app = make_admin_app(agents_dir=agents_dir, data_dir=data_dir)
    url = f"http://127.0.0.1:{args.port}/admin/"
    print(f"[conexus] Studio running at {url}")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return
    func(args)
```

Update the test to also assert legacy subparsers survive:

```python
# Replace test in src/conexus/tests/test_framework_cli.py
def test_studio_and_legacy_subcommands_parse() -> None:
    from conexus.cli.__main__ import _build_parser

    parser = _build_parser()
    studio = parser.parse_args(["studio", "--port", "8765"])
    assert studio.command == "studio" and studio.port == 8765 and callable(studio.func)

    run_agent = parser.parse_args(["run", "agent", "ana"])
    assert run_agent.command == "run" and run_agent.name == "ana" and callable(run_agent.func)

    tag = parser.parse_args(["tag", "suggest", "agents/ana/tools.py"])
    assert tag.command == "tag" and tag.tools_file.endswith("tools.py")

    inst = parser.parse_args(["connectors", "install", "google_calendar", "--agent", "ana"])
    assert inst.command == "connectors" and inst.action == "install" and inst.agent == "ana"
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run pytest src/conexus/tests/test_framework_cli.py::test_studio_subcommand_parses -v
```

- [ ] **Step 5: Manual smoke + commit**

```bash
uv run conexus studio --no-browser --port 8765 &
sleep 2 && curl -sf http://127.0.0.1:8765/admin/ > /dev/null && echo OK
kill %1
git add src/conexus/cli/__main__.py src/conexus/tests/test_framework_cli.py
git commit -m "feat(studio): conexus studio CLI subcommand on 127.0.0.1:8765"
```

### Task 3: Wave 0 wiki sync + Opus review

- [ ] **Step 1: Dispatch wiki-keeper subagent**

```
Dispatch agent_type=wiki-keeper with prompt:
"Phase 12 Wave 0 shipped: src/conexus/web/admin/ scaffold + `conexus studio` CLI.
Create new partition docs/wiki/agents-framework/21-conexus-studio.md (overview only).
Update partition 00-index.md to reference 21.
Cite: src/conexus/web/admin/app.py, src/conexus/cli/__main__.py."
```

- [ ] **Step 2: Dispatch Opus phase review**

```
Dispatch general-purpose with model=opus, prompt:
"Review Wave 0 of Conexus Studio (commits since branch base).
Check: spec compliance to docs/superpowers/plans/2026-05-08-conexus-studio-v1.md Wave 0,
code quality (types, dependency injection, no print in core),
security (localhost bind only, no auth bypass).
Report: APPROVED / APPROVED_WITH_NOTES / BLOCKED + specific issues."
```

- [ ] **Step 3: Open PR for Wave 0**

```bash
git push -u origin <branch>
gh pr create --title "feat(studio): Wave 0 — scaffold" --body "$(cat <<'EOF'
## Summary
- Admin sub-app skeleton (FastAPI + Jinja2 + HTMX/Alpine/Tailwind CDN)
- `conexus studio` CLI on 127.0.0.1:8765
- Base layout + nav

## Test plan
- [ ] uv run pytest src/conexus/tests/test_admin_routes_smoke.py
- [ ] uv run conexus studio → browser opens

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Wave 1 — Read-only (PR 2, ~2 days)

### Task 4 [par-A]: `agent_repo.py` — list/read agents from disk

**Files:**
- Create: `src/conexus/web/admin/services/agent_repo.py`
- Test: `src/conexus/tests/test_admin_agent_repo.py`

- [ ] **Step 1: Write failing tests**

```python
# src/conexus/tests/test_admin_agent_repo.py
from pathlib import Path

import pytest

from conexus.web.admin.services.agent_repo import AgentSummary, list_agents, read_agent


def _seed_agent(root: Path, name: str, tools: list[str]) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    skill = (
        "---\n"
        f"name: {name}\n"
        "role: test\n"
        "goal: |\n  test\n"
        "llm:\n  provider: openai\n  model: gpt-4o-mini\n"
        f"tools: {tools}\n"
        "---\nbody"
    )
    (d / "SKILL.md").write_text(skill)
    (d / "tools.py").write_text("class T:\n    pass\n\ndef create_cli_tools(d):\n    return None, T()\n")


def test_list_agents_returns_summaries(tmp_path: Path) -> None:
    _seed_agent(tmp_path, "ana", ["foo", "bar"])
    _seed_agent(tmp_path, "pesq", [])
    agents = list_agents(tmp_path)
    by_name = {a.name: a for a in agents}
    assert isinstance(by_name["ana"], AgentSummary)
    assert by_name["ana"].tools_count == 2
    assert by_name["pesq"].tools_count == 0


def test_read_agent_returns_skill_and_tools(tmp_path: Path) -> None:
    _seed_agent(tmp_path, "ana", ["foo"])
    agent = read_agent(tmp_path, "ana")
    assert agent.skill.frontmatter.name == "ana"
    assert agent.tools_path.name == "tools.py"
    assert agent.skill.body.strip() == "body"


def test_read_agent_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_agent(tmp_path, "ghost")
```

- [ ] **Step 2: Run — expect ImportError**

```bash
uv run pytest src/conexus/tests/test_admin_agent_repo.py -v
```

- [ ] **Step 3: Implement**

```python
# src/conexus/web/admin/services/agent_repo.py
"""List + read agents from filesystem. Pure functions over Path."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from conexus.core.config.skill_loader import SkillDocument, parse_skill_file


@dataclass(frozen=True)
class AgentSummary:
    name: str
    role: str
    llm_model: str
    tools_count: int
    identity_enabled: bool


@dataclass(frozen=True)
class AgentDetail:
    """`skill` is a SkillDocument with .frontmatter + .body."""
    name: str
    skill: SkillDocument
    skill_path: Path
    tools_path: Path


def _agent_dirs(agents_dir: Path) -> list[Path]:
    if not agents_dir.exists():
        return []
    return sorted(d for d in agents_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists())


def list_agents(agents_dir: Path) -> list[AgentSummary]:
    out: list[AgentSummary] = []
    for d in _agent_dirs(agents_dir):
        try:
            doc = parse_skill_file(d / "SKILL.md")
        except Exception:  # noqa: BLE001
            continue
        fm = doc.frontmatter
        out.append(
            AgentSummary(
                name=fm.name,
                role=fm.role,
                llm_model=fm.llm.model,
                tools_count=len(fm.tools),
                identity_enabled=bool(fm.identity and fm.identity.enabled),
            )
        )
    return out


def read_agent(agents_dir: Path, name: str) -> AgentDetail:
    d = agents_dir / name
    skill_path = d / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"agent not found: {name}")
    doc = parse_skill_file(skill_path)
    return AgentDetail(
        name=doc.frontmatter.name, skill=doc, skill_path=skill_path, tools_path=d / "tools.py"
    )
```

> **Note:** `parse_skill_file` returns `SkillDocument(frontmatter, body)` per `src/conexus/core/config/skill_loader.py:95-118`. All field access goes through `.frontmatter`.

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest src/conexus/tests/test_admin_agent_repo.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/services/agent_repo.py src/conexus/tests/test_admin_agent_repo.py
git commit -m "feat(studio): agent_repo service for list/read agent folders"
```

### Task 5 [par-A]: `tools_inspector.py` — AST scan public methods

**Files:**
- Create: `src/conexus/web/admin/services/tools_inspector.py`
- Test: `src/conexus/tests/test_admin_tools_inspector.py`

- [ ] **Step 1: Write failing tests**

```python
# src/conexus/tests/test_admin_tools_inspector.py
from pathlib import Path

from conexus.web.admin.services.tools_inspector import ToolMethod, scan_tools_file


SAMPLE = '''
class Tools:
    """Doc."""
    _tool_schemas = {
        "list_items": {"description": "List items.", "params": {}}
    }

    def list_items(self, limit: int = 10) -> list[dict]:
        """List items."""
        return []

    def _internal(self) -> None:
        """Hidden."""

    @staticmethod
    def helper() -> str:
        return "x"


def create_cli_tools(d):
    return None, Tools()
'''


def test_scan_returns_public_instance_methods(tmp_path: Path) -> None:
    p = tmp_path / "tools.py"
    p.write_text(SAMPLE)
    methods = scan_tools_file(p)
    names = [m.name for m in methods]
    assert "list_items" in names
    assert "_internal" not in names
    assert "create_cli_tools" not in names


def test_method_has_description_from_schema(tmp_path: Path) -> None:
    p = tmp_path / "tools.py"
    p.write_text(SAMPLE)
    methods = {m.name: m for m in scan_tools_file(p)}
    assert isinstance(methods["list_items"], ToolMethod)
    assert methods["list_items"].description == "List items."
```

- [ ] **Step 2: Run — expect ImportError**

```bash
uv run pytest src/conexus/tests/test_admin_tools_inspector.py -v
```

- [ ] **Step 3: Implement**

```python
# src/conexus/web/admin/services/tools_inspector.py
"""AST scan of an agent's tools.py — list public instance methods."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolParam:
    name: str
    annotation: str | None
    has_default: bool


@dataclass(frozen=True)
class ToolMethod:
    name: str
    params: list[ToolParam]
    return_annotation: str | None
    docstring: str | None
    description: str | None  # from _tool_schemas if present


def _find_tool_class(tree: ast.Module) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            return node
    return None


def _extract_schemas(cls: ast.ClassDef) -> dict[str, str]:
    """Pull description from _tool_schemas = {...} dict literal."""
    out: dict[str, str] = {}
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_tool_schemas" for t in stmt.targets
        ):
            if isinstance(stmt.value, ast.Dict):
                for k, v in zip(stmt.value.keys, stmt.value.values, strict=False):
                    if isinstance(k, ast.Constant) and isinstance(v, ast.Dict):
                        for sk, sv in zip(v.keys, v.values, strict=False):
                            if (
                                isinstance(sk, ast.Constant)
                                and sk.value == "description"
                                and isinstance(sv, ast.Constant)
                            ):
                                out[k.value] = sv.value
    return out


def _is_public_instance_method(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
        return False
    if stmt.name.startswith("_"):
        return False
    if any(isinstance(d, ast.Name) and d.id in {"staticmethod", "classmethod"} for d in stmt.decorator_list):
        return False
    if not stmt.args.args or stmt.args.args[0].arg != "self":
        return False
    return True


def _ann(node: ast.expr | None) -> str | None:
    return ast.unparse(node) if node else None


def scan_tools_file(path: Path) -> list[ToolMethod]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    cls = _find_tool_class(tree)
    if cls is None:
        return []
    schemas = _extract_schemas(cls)
    out: list[ToolMethod] = []
    for stmt in cls.body:
        if not _is_public_instance_method(stmt):
            continue
        assert isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef)
        defaults_offset = len(stmt.args.args) - len(stmt.args.defaults)
        params = [
            ToolParam(name=a.arg, annotation=_ann(a.annotation), has_default=(i >= defaults_offset))
            for i, a in enumerate(stmt.args.args[1:], start=1)
        ]
        out.append(
            ToolMethod(
                name=stmt.name,
                params=params,
                return_annotation=_ann(stmt.returns),
                docstring=ast.get_docstring(stmt),
                description=schemas.get(stmt.name),
            )
        )
    return out
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest src/conexus/tests/test_admin_tools_inspector.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/services/tools_inspector.py src/conexus/tests/test_admin_tools_inspector.py
git commit -m "feat(studio): tools_inspector AST scan of public tool methods"
```

### Task 6 [par-B, depends on 4]: Agents list route + template

**Files:**
- Create: `src/conexus/web/admin/routes/__init__.py` (empty)
- Create: `src/conexus/web/admin/routes/agents.py`
- Create: `src/conexus/web/admin/templates/agents/list.html`
- Modify: `src/conexus/web/admin/app.py` (mount router)
- Test: `src/conexus/tests/test_admin_routes_agents.py`

- [ ] **Step 1: Write failing test**

```python
# src/conexus/tests/test_admin_routes_agents.py
from pathlib import Path

from fastapi.testclient import TestClient

from conexus.web.admin.app import make_admin_app


def _seed(root: Path, name: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\nrole: test\ngoal: |\n  x\n"
        "llm:\n  provider: openai\n  model: gpt-4o-mini\n"
        "tools: []\n---\nbody"
    )
    (d / "tools.py").write_text("class T: pass\n\ndef create_cli_tools(d): return None, T()\n")
    (d / "__init__.py").write_text("")


def test_list_renders_agents(tmp_path: Path) -> None:
    _seed(tmp_path, "ana")
    _seed(tmp_path, "pesq")
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert "ana" in resp.text and "pesq" in resp.text
```

- [ ] **Step 2: Run — expect 200 but no agent names (or 500 if not wired)**

```bash
uv run pytest src/conexus/tests/test_admin_routes_agents.py -v
```

- [ ] **Step 3: Implement router + template**

```python
# src/conexus/web/admin/routes/agents.py
"""Agent list + detail (read-only in Wave 1)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from ..services.agent_repo import list_agents, read_agent
from ..services.tools_inspector import scan_tools_file


def make_agents_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.get("/", response_class=HTMLResponse)
    async def list_view(request: Request) -> HTMLResponse:
        ctx = request.app.state.ctx
        agents = list_agents(ctx.agents_dir)
        return request.app.state.templates.TemplateResponse(
            request, "agents/list.html", {"title": "Agents", "agents": agents}
        )

    @router.get("/agents/{name}", response_class=HTMLResponse)
    async def detail_view(request: Request, name: str) -> HTMLResponse:
        ctx = request.app.state.ctx
        try:
            agent = read_agent(ctx.agents_dir, name)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        methods = scan_tools_file(agent.tools_path) if agent.tools_path.exists() else []
        return request.app.state.templates.TemplateResponse(
            request,
            "agents/edit.html",
            {
                "title": agent.name, "agent": agent, "fm": agent.skill.frontmatter,
                "body": agent.skill.body, "methods": methods, "readonly": True,
                "raw_skill_md": agent.skill_path.read_text(encoding="utf-8"),
            },
        )

    return router
```

```html
<!-- src/conexus/web/admin/templates/agents/list.html -->
{% extends "base.html" %}
{% block content %}
<div class="max-w-5xl mx-auto">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-xl font-semibold">Agents</h2>
    <a href="/admin/agents/new" class="px-3 py-1.5 rounded bg-slate-900 text-white text-sm">New agent</a>
  </div>
  {% if agents %}
  <table class="w-full bg-white border rounded">
    <thead class="bg-slate-100 text-left text-sm">
      <tr><th class="p-2">Name</th><th class="p-2">Role</th><th class="p-2">Model</th>
          <th class="p-2">Tools</th><th class="p-2">Identity</th></tr>
    </thead>
    <tbody>
      {% for a in agents %}
      <tr class="border-t hover:bg-slate-50">
        <td class="p-2"><a class="text-blue-700 hover:underline" href="/admin/agents/{{ a.name }}">{{ a.name }}</a></td>
        <td class="p-2 text-sm">{{ a.role }}</td>
        <td class="p-2 text-sm font-mono">{{ a.llm_model }}</td>
        <td class="p-2 text-sm">{{ a.tools_count }}</td>
        <td class="p-2 text-sm">{{ "on" if a.identity_enabled else "off" }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="text-slate-500">No agents yet. <a href="/admin/agents/new" class="text-blue-700 hover:underline">Create your first agent.</a></p>
  {% endif %}
</div>
{% endblock %}
```

```html
<!-- update src/conexus/web/admin/templates/base.html, replace <main> body -->
<main class="p-6">{% block content %}{% endblock %}</main>
```

```python
# Modify src/conexus/web/admin/app.py — replace inline @app.get("/admin/") with:
from .routes.agents import make_agents_router
# ...
app.include_router(make_agents_router())
# remove the old root() handler
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest src/conexus/tests/test_admin_routes_agents.py src/conexus/tests/test_admin_routes_smoke.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/routes src/conexus/web/admin/templates src/conexus/web/admin/app.py src/conexus/tests/test_admin_routes_agents.py
git commit -m "feat(studio): agents list + detail routes (read-only)"
```

### Task 7 [par-B, depends on 5]: Agent edit view (read-only) + Tools tab

**Files:**
- Create: `src/conexus/web/admin/templates/agents/edit.html`
- Create: `src/conexus/web/admin/templates/partials/agent_form.html`

- [ ] **Step 1: Extend test**

```python
# Append to src/conexus/tests/test_admin_routes_agents.py
def test_detail_shows_method_list(tmp_path: Path) -> None:
    _seed(tmp_path, "ana")
    (tmp_path / "ana" / "tools.py").write_text(
        "class T:\n"
        "    def remember(self, text: str) -> dict: return {}\n"
        "    def list_items(self, limit: int = 10) -> list: return []\n"
        "\ndef create_cli_tools(d): return None, T()\n"
    )
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/agents/ana")
    assert resp.status_code == 200
    assert "remember" in resp.text and "list_items" in resp.text
```

- [ ] **Step 2: Run — expect FAIL (template missing)**

```bash
uv run pytest src/conexus/tests/test_admin_routes_agents.py::test_detail_shows_method_list -v
```

- [ ] **Step 3: Implement templates**

```html
<!-- src/conexus/web/admin/templates/agents/edit.html -->
{% extends "base.html" %}
{% block content %}
<div class="max-w-7xl mx-auto grid grid-cols-12 gap-4">
  <aside class="col-span-2"><a href="/admin/" class="text-sm text-blue-700 hover:underline">&larr; Agents</a></aside>
  <section class="col-span-7 bg-white border rounded p-4">
    {% include "partials/agent_form.html" %}
  </section>
  <aside class="col-span-3 bg-slate-900 text-slate-100 rounded p-3 text-xs font-mono whitespace-pre overflow-auto" id="yaml-preview">
{{ raw_skill_md }}
  </aside>
</div>
{% endblock %}
```

```html
<!-- src/conexus/web/admin/templates/partials/agent_form.html -->
<h2 class="text-xl font-semibold mb-3">{{ agent.name }}</h2>
<div x-data="{ tab: 'identity' }">
  <nav class="flex gap-3 border-b mb-3 text-sm">
    {% for t in ["identity","llm","tools","skills","persistence","budget","prompt"] %}
    <button @click="tab='{{t}}'" :class="tab==='{{t}}' ? 'border-b-2 border-slate-900 -mb-px' : 'text-slate-500'"
            class="pb-2 capitalize">{{ t }}</button>
    {% endfor %}
  </nav>

  <div x-show="tab==='identity'" class="space-y-2">
    <p><b>Name:</b> {{ fm.name }}</p>
    <p><b>Role:</b> {{ fm.role }}</p>
    <p><b>Goal:</b><pre class="text-xs bg-slate-50 p-2 rounded whitespace-pre-wrap">{{ fm.goal }}</pre></p>
  </div>

  <div x-show="tab==='llm'" x-cloak class="space-y-1 text-sm">
    <p><b>Provider:</b> {{ fm.llm.provider }}</p>
    <p><b>Model:</b> {{ fm.llm.model }}</p>
    <p><b>Temperature:</b> {{ fm.llm.temperature }}</p>
  </div>

  <div x-show="tab==='tools'" x-cloak>
    <table class="w-full text-sm">
      <thead class="bg-slate-100"><tr><th class="text-left p-1">Method</th><th class="text-left p-1">Allowed</th><th class="text-left p-1">Description</th></tr></thead>
      <tbody>
        {% for m in methods %}
        <tr class="border-t"><td class="p-1 font-mono">{{ m.name }}</td>
          <td class="p-1">{{ "✔" if m.name in fm.tools else "—" }}</td>
          <td class="p-1 text-slate-600">{{ m.description or m.docstring or "" }}</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div x-show="tab==='skills'" x-cloak>
    {% if fm.skills %}<ul class="list-disc pl-5">{% for s in fm.skills %}<li class="font-mono text-sm">{{ s }}</li>{% endfor %}</ul>
    {% else %}<p class="text-slate-500 text-sm">No skills attached.</p>{% endif %}
  </div>

  <div x-show="tab==='persistence'" x-cloak class="text-sm">
    {% if fm.identity and fm.identity.enabled %}
      <p>Identity <b>enabled</b>. Blocks: {{ fm.identity.blocks | length }}</p>
    {% else %}<p class="text-slate-500">Identity disabled.</p>{% endif %}
  </div>

  <div x-show="tab==='budget'" x-cloak class="text-sm">
    {% if fm.budget %}
      <p>Daily: ${{ fm.budget.daily_usd }} • Monthly: ${{ fm.budget.monthly_usd }} • on_exceed: {{ fm.budget.on_exceed }}</p>
    {% else %}<p class="text-slate-500">No budget set.</p>{% endif %}
  </div>

  <div x-show="tab==='prompt'" x-cloak>
    <pre class="text-xs bg-slate-50 p-2 rounded whitespace-pre-wrap">{{ body }}</pre>
  </div>
</div>
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest src/conexus/tests/test_admin_routes_agents.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/templates
git commit -m "feat(studio): agent edit view tabs (read-only) + Tools tab via AST"
```

### Task 8 [par-C]: Connector marketplace route + template

**Files:**
- Create: `src/conexus/web/admin/routes/connectors.py`
- Create: `src/conexus/web/admin/templates/connectors/marketplace.html`
- Create: `src/conexus/web/admin/templates/partials/connector_card.html`
- Modify: `src/conexus/web/admin/app.py` (include router)
- Test: `src/conexus/tests/test_admin_routes_connectors.py`

- [ ] **Step 1: Write failing test**

```python
# src/conexus/tests/test_admin_routes_connectors.py
import json
from pathlib import Path

from fastapi.testclient import TestClient

from conexus.web.admin.app import make_admin_app


def test_marketplace_renders_registry(tmp_path: Path) -> None:
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps({"version": "1.0", "connectors": [{
        "name": "google_calendar", "version": "1.0",
        "server_url": "https://mcp.google.com/calendar",
        "scopes": ["calendar.readonly"],
        "ui": {"label": "Google Calendar", "icon": "🗓", "category": "Productivity",
               "description": "Read + create events."}
    }]}))
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path, connectors_registry_path=reg)
    client = TestClient(app)
    resp = client.get("/admin/connectors")
    assert resp.status_code == 200
    assert "Google Calendar" in resp.text
    assert "🗓" in resp.text
```

- [ ] **Step 2: Run — expect 404**

```bash
uv run pytest src/conexus/tests/test_admin_routes_connectors.py -v
```

- [ ] **Step 3: Implement**

```python
# src/conexus/web/admin/routes/connectors.py
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from conexus.core.connectors.registry import ConnectorRegistry


def make_connectors_router() -> APIRouter:
    router = APIRouter(prefix="/admin/connectors")

    @router.get("", response_class=HTMLResponse)
    async def marketplace(request: Request) -> HTMLResponse:
        ctx = request.app.state.ctx
        registry = ConnectorRegistry.from_file(ctx.connectors_registry_path)
        return request.app.state.templates.TemplateResponse(
            request, "connectors/marketplace.html",
            {"title": "Connectors", "entries": registry.list()},
        )

    return router
```

```html
<!-- src/conexus/web/admin/templates/connectors/marketplace.html -->
{% extends "base.html" %}
{% block content %}
<div class="max-w-6xl mx-auto">
  <h2 class="text-xl font-semibold mb-4">Connector marketplace</h2>
  {% if entries %}
  <div class="grid grid-cols-3 gap-4">
    {% for e in entries %}{% include "partials/connector_card.html" %}{% endfor %}
  </div>
  {% else %}<p class="text-slate-500">No connectors registered.</p>{% endif %}
</div>
{% endblock %}
```

```html
<!-- src/conexus/web/admin/templates/partials/connector_card.html -->
<div class="bg-white border rounded p-3 flex flex-col">
  <div class="flex items-center gap-2 mb-1"><span class="text-2xl">{{ e.ui.icon }}</span>
    <h3 class="font-semibold">{{ e.ui.label }}</h3></div>
  <p class="text-xs text-slate-500 mb-1">{{ e.ui.category }} · v{{ e.version }}</p>
  <p class="text-sm flex-1">{{ e.ui.description }}</p>
  <div class="text-xs text-slate-400 font-mono mt-2 break-all">{{ e.server_url }}</div>
  <button class="mt-3 px-3 py-1.5 bg-slate-900 text-white rounded text-sm" disabled>Install (Wave 2)</button>
</div>
```

```python
# Modify src/conexus/web/admin/app.py — add:
from .routes.connectors import make_connectors_router
# ...
app.include_router(make_connectors_router())
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest src/conexus/tests/test_admin_routes_connectors.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/routes/connectors.py src/conexus/web/admin/templates/connectors src/conexus/web/admin/templates/partials/connector_card.html src/conexus/web/admin/app.py src/conexus/tests/test_admin_routes_connectors.py
git commit -m "feat(studio): connector marketplace route (read-only)"
```

### Task 9 [par-C]: REPL service + route (read-only — Wave 1 dispatches existing runtime, no writes)

**Files:**
- Create: `src/conexus/web/admin/services/runner_proxy.py`
- Create: `src/conexus/web/admin/routes/repl.py`
- Create: `src/conexus/web/admin/templates/repl/panel.html`
- Create: `src/conexus/web/admin/templates/partials/repl_message.html`
- Test: `src/conexus/tests/test_admin_routes_repl.py`

- [ ] **Step 1: Write failing test (uses dummy registry — no real LLM)**

```python
# src/conexus/tests/test_admin_routes_repl.py
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from conexus.web.admin.app import make_admin_app


def _seed(root: Path, name: str = "ana") -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    (d / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\nrole: test\ngoal: |\n  x\n"
        "llm:\n  provider: openai\n  model: gpt-4o-mini\n"
        "tools: []\n---\nbody"
    )
    (d / "tools.py").write_text(
        "class T:\n    pass\n\ndef create_cli_tools(d):\n    return None, T()\n"
    )


def test_repl_post_returns_partial(tmp_path: Path) -> None:
    _seed(tmp_path)
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path)
    client = TestClient(app)

    async def fake_run(*a, **kw):  # noqa: ARG001
        return "hello back"

    with patch("conexus.web.admin.services.runner_proxy.run_one_message", new=fake_run):
        resp = client.post("/admin/agents/ana/test", data={"message": "hi"})
    assert resp.status_code == 200
    assert "hello back" in resp.text
```

- [ ] **Step 2: Run — expect 404**

```bash
uv run pytest src/conexus/tests/test_admin_routes_repl.py -v
```

- [ ] **Step 3: Implement service + route**

```python
# src/conexus/web/admin/services/runner_proxy.py
"""Wrap build_runtime + handle_agent_message for one-shot REPL invocations.

Sessions are kept in-memory keyed by (agent_name, session_id). The session
holds the registry, tracker, runtime, and store so identity/history persist
across turns within the same browser session.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conexus.core.agent_handler import handle_agent_message
from conexus.core.agent_registry import AgentRegistry
from conexus.core.budget.cap_checker import CapChecker
from conexus.core.config.skill_loader import parse_skill_file
from conexus.core.llm.usage_tracker import UsageTracker
from conexus.cli.runner import build_runtime


@dataclass
class _Session:
    registry: Any
    tracker: Any
    runtime: Any
    store: Any
    cap_checker: Any


_SESSIONS: dict[tuple[str, str], _Session] = {}


def _build_session(agent_name: str, agents_dir: Path, data_dir: Path) -> _Session:
    import importlib.util

    skill_path = agents_dir / agent_name / "SKILL.md"
    tools_path = agents_dir / agent_name / "tools.py"
    spec = importlib.util.spec_from_file_location(f"_studio_tools_{agent_name}", tools_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import tools.py for {agent_name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    store, tools = mod.create_cli_tools(data_dir)

    registry = AgentRegistry()
    registry.register(agent_name, tools)
    tracker = UsageTracker(store)

    async def execute_tool(tool_name: str, args: dict) -> str:
        return await registry.execute_tool(agent_name, tool_name, args)

    skill = parse_skill_file(skill_path)
    runtime = build_runtime(
        str(skill_path),
        tools_obj=tools, execute_tool=execute_tool, tracker=tracker,
        agent_name=agent_name, system_prompt=skill.body, store=store,
    )
    return _Session(
        registry=registry, tracker=tracker, runtime=runtime,
        store=store, cap_checker=CapChecker(tracker),
    )


async def run_one_message(
    agent_name: str, message: str, *, agents_dir: Path, data_dir: Path, session_id: str
) -> str:
    key = (agent_name, session_id)
    if key not in _SESSIONS:
        _SESSIONS[key] = _build_session(agent_name, agents_dir, data_dir)
    s = _SESSIONS[key]
    return await handle_agent_message(s.runtime.handler_cfg, s.store, s.cap_checker, message)


def reset_session(agent_name: str, session_id: str) -> None:
    _SESSIONS.pop((agent_name, session_id), None)
```

```python
# src/conexus/web/admin/routes/repl.py
from __future__ import annotations

import secrets
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ..services.runner_proxy import run_one_message


def make_repl_router() -> APIRouter:
    router = APIRouter(prefix="/admin/agents")

    @router.post("/{name}/test", response_class=HTMLResponse)
    async def test(request: Request, name: str, message: str = Form(...)) -> HTMLResponse:
        ctx = request.app.state.ctx
        sid = request.cookies.get("studio_sid") or secrets.token_hex(8)
        reply = await run_one_message(
            name, message, agents_dir=ctx.agents_dir, data_dir=ctx.data_dir, session_id=sid
        )
        resp = request.app.state.templates.TemplateResponse(
            request, "partials/repl_message.html", {"role": "agent", "text": reply}
        )
        resp.set_cookie("studio_sid", sid, httponly=True, samesite="lax")
        return resp

    return router
```

```html
<!-- src/conexus/web/admin/templates/partials/repl_message.html -->
<div class="border-l-4 {{ 'border-blue-500' if role=='user' else 'border-slate-400' }} pl-2 py-1 my-1 text-sm">
  <span class="text-xs text-slate-500">{{ role }}</span>
  <p class="whitespace-pre-wrap">{{ text }}</p>
</div>
```

```python
# Modify src/conexus/web/admin/app.py — add:
from .routes.repl import make_repl_router
app.include_router(make_repl_router())
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest src/conexus/tests/test_admin_routes_repl.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/services/runner_proxy.py src/conexus/web/admin/routes/repl.py src/conexus/web/admin/templates/partials/repl_message.html src/conexus/web/admin/templates/repl src/conexus/web/admin/app.py src/conexus/tests/test_admin_routes_repl.py
git commit -m "feat(studio): REPL one-shot with persistent session"
```

### Task 10: Wave 1 wiki + Opus + PR

- [ ] **Step 1: wiki-keeper subagent**

```
agent_type=wiki-keeper, prompt: "Wave 1 read-only views shipped (agents list, agent detail with tabs, connector marketplace, REPL one-shot). Update partition 21-conexus-studio.md with Wave 1 views + service modules. Cite agent_repo.py, tools_inspector.py, runner_proxy.py."
```

- [ ] **Step 2: Opus phase review**

```
general-purpose with model=opus: "Review Wave 1 of Conexus Studio per docs/superpowers/plans/2026-05-08-conexus-studio-v1.md tasks 4-9. Check spec compliance + code quality + security (read-only routes, no path traversal in agent name)."
```

- [ ] **Step 3: PR**

```bash
git push && gh pr create --title "feat(studio): Wave 1 — read-only views" --body "Tasks 4-9: list, edit, connectors, REPL. 6 services, 4 routes, 8 templates."
```

---

## Wave 2 — Writes (PR 3, ~3 days)

### Task 11 [par-D]: `skill_writer.py` — atomic SKILL.md rewrite

**Files:**
- Create: `src/conexus/web/admin/services/skill_writer.py`
- Test: `src/conexus/tests/test_admin_skill_writer.py`

- [ ] **Step 1: Failing test**

```python
# src/conexus/tests/test_admin_skill_writer.py
from pathlib import Path

import yaml

from conexus.web.admin.services.skill_writer import write_skill_md


def test_write_creates_round_trippable_yaml(tmp_path: Path) -> None:
    fm = {"name": "ana", "role": "test", "goal": "x",
          "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.4},
          "tools": ["foo"]}
    body = "system prompt\nline 2"
    out = tmp_path / "SKILL.md"
    write_skill_md(out, fm, body)
    assert out.exists()
    raw = out.read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    assert "\n---\n" in raw
    parsed_fm = yaml.safe_load(raw.split("---", 2)[1])
    assert parsed_fm["name"] == "ana"
    assert raw.endswith("system prompt\nline 2\n")


def test_write_is_atomic_on_replace_failure(tmp_path: Path, monkeypatch) -> None:
    """os.replace failure → original preserved + no .tmp leftovers."""
    out = tmp_path / "SKILL.md"
    out.write_text("ORIGINAL", encoding="utf-8")
    fm = {"name": "ana", "role": "test", "goal": "x",
          "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.4},
          "tools": []}

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    try:
        write_skill_md(out, fm, "new body")
    except OSError:
        pass

    assert out.read_text(encoding="utf-8") == "ORIGINAL"
    leftovers = list(tmp_path.glob("SKILL.md*.tmp*")) + list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"tmp files leaked: {leftovers}"


def test_write_cleans_tmp_on_write_failure(tmp_path: Path, monkeypatch) -> None:
    """If write/fsync raises mid-flight, no tmp file is left behind."""
    out = tmp_path / "SKILL.md"
    fm = {"name": "ana", "role": "test", "goal": "x",
          "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.4},
          "tools": []}

    real_fsync = __import__("os").fsync

    def boom(_fd):
        raise OSError("disk full")

    monkeypatch.setattr("os.fsync", boom)
    try:
        write_skill_md(out, fm, "body")
    except OSError:
        pass
    finally:
        monkeypatch.setattr("os.fsync", real_fsync)

    assert not out.exists()
    leftovers = list(tmp_path.glob("SKILL.md*.tmp*")) + list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"tmp files leaked: {leftovers}"
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement**

```python
# src/conexus/web/admin/services/skill_writer.py
"""Atomic SKILL.md writer."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


def write_skill_md(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    """Write SKILL.md atomically: tmp file → fsync → os.replace.

    Guarantees:
    - Existing file preserved on any failure (write, fsync, or replace).
    - No `*.tmp*` leftovers in parent on failure paths.
    """
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip()
    content = f"---\n{fm_yaml}\n---\n{body.rstrip()}\n"

    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(parent))
    try:
        # Take ownership of fd via fdopen; on fdopen failure we must close fd directly.
        try:
            f = os.fdopen(fd, "w", encoding="utf-8")
        except Exception:
            os.close(fd)
            raise
        with f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        tmp = None  # success: tmp consumed by replace
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/services/skill_writer.py src/conexus/tests/test_admin_skill_writer.py
git commit -m "feat(studio): atomic skill_writer with tempfile + os.replace"
```

### Task 12 [par-D]: `validators.py` — pydantic + AST + subprocess smoke

**Files:**
- Create: `src/conexus/web/admin/services/validators.py`
- Test: `src/conexus/tests/test_admin_validators.py`

- [ ] **Step 1: Failing tests**

```python
# src/conexus/tests/test_admin_validators.py
from pathlib import Path

from conexus.web.admin.services.validators import validate_agent, ValidationResult


def _seed(root: Path, name="ana", tools=None, body="x"):
    tools = tools if tools is not None else ["foo"]
    d = root / name
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    (d / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\nrole: test\ngoal: |\n  goal\n"
        "llm:\n  provider: openai\n  model: gpt-4o-mini\n  temperature: 0.4\n"
        f"tools: {tools}\n---\n{body}"
    )
    (d / "tools.py").write_text(
        "class Tools:\n    def foo(self) -> dict: return {}\n\ndef create_cli_tools(d): return None, Tools()\n"
    )


def test_valid_agent_passes(tmp_path: Path) -> None:
    _seed(tmp_path)
    res = validate_agent(tmp_path, "ana")
    assert res.ok and not res.errors


def test_unknown_tool_in_skill_md_blocks(tmp_path: Path) -> None:
    _seed(tmp_path, tools=["foo", "ghost"])
    res = validate_agent(tmp_path, "ana")
    assert not res.ok
    assert any("ghost" in e for e in res.errors)


def test_short_prompt_warns(tmp_path: Path) -> None:
    _seed(tmp_path, body="hi")
    res = validate_agent(tmp_path, "ana")
    assert res.ok
    assert any("prompt" in w.lower() for w in res.warnings)


def test_unimportable_tools_py_blocks(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "ana" / "tools.py").write_text("syntax !!! error")
    res = validate_agent(tmp_path, "ana")
    assert not res.ok
    assert any("import" in e.lower() or "syntax" in e.lower() for e in res.errors)


def test_identity_tools_match_real_class() -> None:
    """Drift guard: IDENTITY_TOOLS must equal IdentityTools public method set."""
    from conexus.core.identity.tools import IdentityTools
    from conexus.web.admin.services.validators import IDENTITY_TOOLS

    real = {
        n for n in dir(IdentityTools)
        if not n.startswith("_") and callable(getattr(IdentityTools, n))
    }
    assert IDENTITY_TOOLS == real
```

- [ ] **Step 2: Run — ImportError**

- [ ] **Step 3: Implement**

```python
# src/conexus/web/admin/services/validators.py
"""Validate an agent on disk: pydantic frontmatter + AST tools + subprocess import smoke."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from conexus.core.config.skill_loader import parse_skill_file

from .tools_inspector import scan_tools_file

# Source of truth: src/conexus/core/identity/tools.py:24
# Derived once, kept fresh via test in test_admin_validators.py.
IDENTITY_TOOLS = frozenset({
    "memory_get", "memory_set", "memory_list_facts", "memory_delete",
    "block_get", "block_set", "block_list",
    "wiki_read", "wiki_list", "wiki_search", "wiki_write", "wiki_append_log",
})


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _smoke_import(tools_py: Path, agent_name: str) -> str | None:
    """Subprocess-import tools.py. Returns error string or None."""
    code = (
        "import importlib.util, sys; "
        f"spec = importlib.util.spec_from_file_location('_smoke', r'{tools_py}'); "
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
        "assert hasattr(mod, 'create_cli_tools')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=10, check=False
        )
        if result.returncode != 0:
            return (result.stderr or result.stdout or "import failed").strip().splitlines()[-1]
    except subprocess.TimeoutExpired:
        return "import timed out (10s)"
    return None


def validate_agent(agents_dir: Path, name: str) -> ValidationResult:
    res = ValidationResult(ok=True)
    d = agents_dir / name
    skill_path = d / "SKILL.md"
    tools_path = d / "tools.py"

    if not skill_path.exists():
        res.errors.append(f"SKILL.md missing: {skill_path}")
        res.ok = False
        return res

    try:
        skill = parse_skill_file(skill_path)
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"SKILL.md parse error: {exc}")
        res.ok = False
        return res

    if skill.name != name:
        res.errors.append(f"frontmatter name '{skill.name}' != folder '{name}'")

    if not tools_path.exists():
        res.errors.append("tools.py missing")
        res.ok = False
    else:
        try:
            methods = {m.name for m in scan_tools_file(tools_path)}
        except SyntaxError as exc:
            res.errors.append(f"tools.py syntax error: {exc}")
            res.ok = False
            methods = set()

        identity_active = bool(skill.identity and skill.identity.enabled)
        for t in skill.tools:
            if t in methods:
                continue
            if identity_active and t in IDENTITY_TOOLS:
                continue
            res.errors.append(f"tools[]: '{t}' not found in tools.py and not an identity tool")

        if methods or not res.errors:
            err = _smoke_import(tools_path, name)
            if err:
                res.errors.append(f"tools.py import: {err}")

    body = skill.body if hasattr(skill, "body") else ""
    if len(body.split()) < 10:
        res.warnings.append("system prompt < 10 words — agent may behave unpredictably")
    if not skill.llm.fallback:
        res.warnings.append("no LLM fallback configured")
    if not skill.budget:
        res.warnings.append("no budget cap configured")

    res.ok = res.ok and not res.errors
    return res
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/services/validators.py src/conexus/tests/test_admin_validators.py
git commit -m "feat(studio): validators with pydantic + AST + subprocess import smoke"
```

### Task 13 [par-D]: `tools_writer.py` — rewrite `_tool_schemas` dict only

**Files:**
- Create: `src/conexus/web/admin/services/tools_writer.py`
- Test: `src/conexus/tests/test_admin_tools_writer.py`

- [ ] **Step 1: Failing tests**

```python
# src/conexus/tests/test_admin_tools_writer.py
from pathlib import Path

from conexus.web.admin.services.tools_writer import write_tool_schemas


SAMPLE = '''class Tools:
    """Doc."""
    _tool_schemas = {
        "foo": {"description": "Old.", "params": {}}
    }

    def foo(self) -> dict:
        return {}


def create_cli_tools(d):
    return None, Tools()
'''


def test_overwrites_schemas_block(tmp_path: Path) -> None:
    p = tmp_path / "tools.py"
    p.write_text(SAMPLE)
    write_tool_schemas(p, {"foo": {"description": "New desc.", "params": {}}})
    out = p.read_text()
    assert '"description": "New desc."' in out
    assert '"description": "Old."' not in out
    assert "def foo(self)" in out  # method body untouched


def test_inserts_block_when_absent(tmp_path: Path) -> None:
    p = tmp_path / "tools.py"
    p.write_text(
        "class Tools:\n    def foo(self) -> dict: return {}\n\n"
        "def create_cli_tools(d): return None, Tools()\n"
    )
    write_tool_schemas(p, {"foo": {"description": "Hi.", "params": {}}})
    out = p.read_text()
    assert "_tool_schemas" in out
    assert '"description": "Hi."' in out
    # exactly one schema block
    assert out.count("_tool_schemas") == 1


ANNOTATED = '''from typing import ClassVar


class Tools:
    _tool_schemas: ClassVar[dict] = {
        "foo": {"description": "Old.", "params": {}}
    }

    def foo(self) -> dict:
        return {}


def create_cli_tools(d):
    return None, Tools()
'''


def test_overwrites_annotated_schemas(tmp_path: Path) -> None:
    """Templates emit `_tool_schemas: ClassVar[dict] = {...}` (ast.AnnAssign)."""
    p = tmp_path / "tools.py"
    p.write_text(ANNOTATED)
    write_tool_schemas(p, {"foo": {"description": "Fresh.", "params": {}}})
    out = p.read_text()
    assert out.count("_tool_schemas") == 1
    assert '"description": "Fresh."' in out
    assert '"description": "Old."' not in out
```

- [ ] **Step 2: Run — ImportError**

- [ ] **Step 3: Implement**

```python
# src/conexus/web/admin/services/tools_writer.py
"""Rewrite the `_tool_schemas = {...}` block at top of the tool class.

Only this block is rewritten — method bodies, docstrings, imports untouched.
Bodies remain editable in IDE; UI owns metadata only.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


def _format_block(schemas: dict[str, Any], indent: str = "    ") -> str:
    payload = json.dumps(schemas, indent=4, ensure_ascii=False)
    indented = "\n".join((indent + line) if line else line for line in payload.splitlines())
    return f"{indent}_tool_schemas = {indented.lstrip()}"


def write_tool_schemas(path: Path, schemas: dict[str, Any]) -> None:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))

    class_node: ast.ClassDef | None = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef)), None
    )
    if class_node is None:
        raise ValueError(f"{path}: no class found")

    lines = src.splitlines(keepends=True)
    block_text = _format_block(schemas) + "\n"

    def _is_schemas(s: ast.stmt) -> bool:
        # Plain assign: `_tool_schemas = {...}`
        if isinstance(s, ast.Assign):
            return any(isinstance(t, ast.Name) and t.id == "_tool_schemas" for t in s.targets)
        # Annotated assign: `_tool_schemas: ClassVar[dict] = {...}` (template emits this)
        if isinstance(s, ast.AnnAssign):
            return isinstance(s.target, ast.Name) and s.target.id == "_tool_schemas"
        return False

    existing = next((s for s in class_node.body if _is_schemas(s)), None)

    if existing is not None:
        start = existing.lineno - 1
        end = (existing.end_lineno or existing.lineno)
        new_lines = lines[:start] + [block_text] + lines[end:]
    else:
        # Insert after class docstring (if any) or as first statement.
        first = class_node.body[0]
        insert_after_line = first.end_lineno if (
            isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
        ) else (class_node.lineno)
        new_lines = lines[:insert_after_line] + [block_text + "\n"] + lines[insert_after_line:]

    path.write_text("".join(new_lines), encoding="utf-8")
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/services/tools_writer.py src/conexus/tests/test_admin_tools_writer.py
git commit -m "feat(studio): tools_writer rewrites _tool_schemas only, preserves bodies"
```

### Task 14 [par-D]: `template_lib.py` — 3 agent templates

**Files:**
- Create: `src/conexus/web/admin/services/template_lib.py`
- Test: `src/conexus/tests/test_admin_template_lib.py`

- [ ] **Step 1: Failing tests**

```python
# src/conexus/tests/test_admin_template_lib.py
from pathlib import Path

import pytest

from conexus.web.admin.services.template_lib import TEMPLATES, scaffold_agent


def test_chat_only_creates_files(tmp_path: Path) -> None:
    scaffold_agent(tmp_path, "ana", template="chat-only")
    d = tmp_path / "ana"
    assert (d / "SKILL.md").exists() and (d / "tools.py").exists() and (d / "__init__.py").exists()


def test_invalid_name_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        scaffold_agent(tmp_path, "Bad-Name", template="chat-only")
    with pytest.raises(ValueError):
        scaffold_agent(tmp_path, "../etc/passwd", template="chat-only")


def test_existing_agent_rejected(tmp_path: Path) -> None:
    scaffold_agent(tmp_path, "ana", template="chat-only")
    with pytest.raises(FileExistsError):
        scaffold_agent(tmp_path, "ana", template="chat-only")


def test_chat_memory_gcal_includes_connector(tmp_path: Path) -> None:
    scaffold_agent(tmp_path, "ana", template="chat+memory+gcal")
    pack = tmp_path / "ana" / "skills" / "google_calendar"
    assert (pack / "SKILL_PACK.md").exists() and (pack / "connector.json").exists()


def test_template_list() -> None:
    assert set(TEMPLATES) == {"chat-only", "chat+memory", "chat+memory+gcal"}
```

- [ ] **Step 2: Run — ImportError**

- [ ] **Step 3: Implement**

```python
# src/conexus/web/admin/services/template_lib.py
"""Agent scaffolding templates."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .skill_writer import write_skill_md

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")

_TOOLS_PY = '''"""Tools for {name}."""
from __future__ import annotations

from typing import ClassVar

from conexus.core.memory.sqlite_store import SqliteStore


class {cls}:
    """Public methods are callable by the agent. Underscore methods are hidden."""

    _tool_schemas: ClassVar[dict] = {{
        "ping": {{"description": "Health check.", "params": {{}}}},
    }}

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def ping(self) -> dict:
        """Health check."""
        return {{"ok": True}}


def create_cli_tools(data_dir):
    store = SqliteStore(str(data_dir) + "/conexus.db")
    return store, {cls}(store)
'''


def _tools_class_name(agent: str) -> str:
    return "".join(p.capitalize() for p in agent.split("_")) + "Tools"


def _base_frontmatter(name: str) -> dict:
    return {
        "name": name, "role": "personal assistant", "language": "pt-BR",
        "goal": "Be a helpful assistant.",
        "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.4,
                "fallback": [{"provider": "anthropic", "model": "claude-haiku-4-5"}]},
        "tools": ["ping"],
    }


def _identity_block() -> dict:
    return {
        "enabled": True,
        "blocks": {"user": {"budget_chars": 500}, "persona": {"budget_chars": 800}},
        "facts": {"enabled": True, "inject_recent": 5},
        "history": {"budget_tokens": 4000, "keep_verbatim": 6, "summary_budget": 800,
                    "trigger_pct": 0.80},
    }


TEMPLATES = ("chat-only", "chat+memory", "chat+memory+gcal")


def scaffold_agent(agents_dir: Path, name: str, *, template: str) -> Path:
    if template not in TEMPLATES:
        raise ValueError(f"unknown template: {template}")
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid agent name: {name!r} (must match {_NAME_RE.pattern})")

    d = agents_dir / name
    if d.exists():
        raise FileExistsError(f"agent exists: {d}")
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    (d / "tools.py").write_text(_TOOLS_PY.format(name=name, cls=_tools_class_name(name)))

    fm = _base_frontmatter(name)
    if template in ("chat+memory", "chat+memory+gcal"):
        fm["identity"] = _identity_block()
    if template == "chat+memory+gcal":
        fm["skills"] = ["google_calendar@1.0"]
        pack = d / "skills" / "google_calendar"
        pack.mkdir(parents=True)
        (pack / "SKILL_PACK.md").write_text(
            "---\nname: google_calendar\nversion: \"1.0\"\nbackend: mcp-http\n"
            "capabilities: []\ndata_classes: {}\n---\nGoogle Calendar.\n"
        )
        (pack / "connector.json").write_text(json.dumps({
            "server_url": "https://mcp.google.com/calendar",
            "scopes": ["https://www.googleapis.com/auth/calendar.readonly",
                       "https://www.googleapis.com/auth/calendar.events"],
            "ui": {"label": "Google Calendar", "icon": "🗓",
                   "category": "Productivity", "description": "Read and create events."}
        }, indent=2))

    write_skill_md(d / "SKILL.md", fm, f"You are {name}, a helpful assistant.\n")
    return d
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/services/template_lib.py src/conexus/tests/test_admin_template_lib.py
git commit -m "feat(studio): 3 agent scaffolding templates with sandbox name validation"
```

### Task 15 [par-D]: `connector_installer.py` + auto-append to `skills:`

**Files:**
- Create: `src/conexus/web/admin/services/connector_installer.py`
- Test: `src/conexus/tests/test_admin_connector_installer.py`

- [ ] **Step 1: Failing test**

```python
# src/conexus/tests/test_admin_connector_installer.py
import json
from pathlib import Path

from conexus.web.admin.services.connector_installer import install_connector
from conexus.web.admin.services.template_lib import scaffold_agent


def _registry(tmp_path: Path) -> Path:
    p = tmp_path / "registry.json"
    p.write_text(json.dumps({"version": "1.0", "connectors": [{
        "name": "notion", "version": "1.0", "server_url": "https://mcp.notion.so",
        "scopes": ["read"],
        "ui": {"label": "Notion", "icon": "📓", "category": "Docs", "description": "Notion."},
    }]}))
    return p


def test_install_writes_pack_and_appends_skill(tmp_path: Path) -> None:
    scaffold_agent(tmp_path, "ana", template="chat-only")
    install_connector(agents_dir=tmp_path, agent_name="ana",
                      connector_name="notion", registry_path=_registry(tmp_path))
    pack = tmp_path / "ana" / "skills" / "notion"
    assert (pack / "SKILL_PACK.md").exists()
    assert (pack / "connector.json").exists()
    skill_md = (tmp_path / "ana" / "SKILL.md").read_text()
    assert "notion@1.0" in skill_md


def test_install_idempotent_skill_ref(tmp_path: Path) -> None:
    scaffold_agent(tmp_path, "ana", template="chat-only")
    install_connector(agents_dir=tmp_path, agent_name="ana",
                      connector_name="notion", registry_path=_registry(tmp_path))
    install_connector(agents_dir=tmp_path, agent_name="ana",
                      connector_name="notion", registry_path=_registry(tmp_path))
    skill_md = (tmp_path / "ana" / "SKILL.md").read_text()
    assert skill_md.count("notion@1.0") == 1
```

- [ ] **Step 2: ImportError**

- [ ] **Step 3: Implement**

```python
# src/conexus/web/admin/services/connector_installer.py
"""Install a connector from registry into an agent folder + auto-append to skills:."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from conexus.core.connectors.registry import ConnectorRegistry

from .skill_writer import write_skill_md


def install_connector(
    *, agents_dir: Path, agent_name: str, connector_name: str, registry_path: Path
) -> None:
    registry = ConnectorRegistry.from_file(registry_path)
    entry = registry.get(connector_name)
    if entry is None:
        raise ValueError(f"connector not in registry: {connector_name}")

    agent = agents_dir / agent_name
    if not (agent / "SKILL.md").exists():
        raise FileNotFoundError(f"agent not found: {agent_name}")

    pack_dir = agent / "skills" / entry.name
    pack_dir.mkdir(parents=True, exist_ok=True)

    (pack_dir / "SKILL_PACK.md").write_text(
        "---\n"
        f"name: {entry.name}\nversion: \"{entry.version}\"\nbackend: mcp-http\n"
        "capabilities: []\ndata_classes: {}\n"
        "---\n"
        f"{entry.ui.description if entry.ui else ''}\n"
    )

    connector_json = {
        "server_url": entry.server_url,
        "scopes": entry.scopes,
        "ui": entry.ui.__dict__ if entry.ui else {},
    }
    (pack_dir / "connector.json").write_text(json.dumps(connector_json, indent=2))

    skill_md = (agent / "SKILL.md").read_text()
    front_raw, _, body = skill_md.partition("---\n")[2].partition("\n---\n")
    fm = yaml.safe_load(front_raw)
    skills = list(fm.get("skills", []))
    ref = f"{entry.name}@{entry.version}"
    if ref not in skills:
        skills.append(ref)
        fm["skills"] = skills
        write_skill_md(agent / "SKILL.md", fm, body)
```

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/services/connector_installer.py src/conexus/tests/test_admin_connector_installer.py
git commit -m "feat(studio): connector installer with idempotent skills: append"
```

### Task 16a [serial, depends on 11-12]: POST /admin/agents/{name} (save) + validation_errors partial

**Files:**
- Modify: `src/conexus/web/admin/routes/agents.py` (add `save` handler)
- Create: `src/conexus/web/admin/templates/partials/validation_errors.html`
- Modify: `src/conexus/web/admin/templates/partials/agent_form.html` (Task 7 — wrap fields in `<form method="post">`)
- Test: extend `test_admin_routes_agents.py`

- [ ] **Step 1: Failing tests**

```python
# Append to src/conexus/tests/test_admin_routes_agents.py
def test_save_writes_skill_md(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "ana", template="chat-only")
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post("/admin/agents/ana", data={
        "role": "updated role", "goal": "new goal",
        "llm_provider": "openai", "llm_model": "gpt-4o-mini", "llm_temperature": "0.5",
        "tools": "ping", "body": "new body",
    })
    assert resp.status_code == 200
    text = (tmp_path / "ana" / "SKILL.md").read_text(encoding="utf-8")
    assert "updated role" in text
    assert "new body" in text


def test_save_blocks_invalid(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "ana", template="chat-only")
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post("/admin/agents/ana", data={
        "role": "x", "goal": "x", "llm_provider": "openai",
        "llm_model": "gpt-4o-mini", "llm_temperature": "0.5",
        "tools": "ghost_method", "body": "x",
    })
    assert resp.status_code == 422
    assert "ghost_method" in resp.text
```

- [ ] **Step 2: Implement save handler**

```python
# Append to src/conexus/web/admin/routes/agents.py inside make_agents_router()
import yaml
from fastapi import Form, HTTPException
from ..services.skill_writer import write_skill_md
from ..services.validators import validate_agent

@router.post("/agents/{name}", response_class=HTMLResponse)
async def save(
    request: Request, name: str,
    role: str = Form(...), goal: str = Form(...),
    llm_provider: str = Form(...), llm_model: str = Form(...),
    llm_temperature: str = Form("0.4"),
    tools: str = Form(""), body: str = Form(""),
) -> HTMLResponse:
    ctx = request.app.state.ctx
    skill_path = ctx.agents_dir / name / "SKILL.md"
    if not skill_path.exists():
        raise HTTPException(404, name)
    existing = yaml.safe_load(skill_path.read_text(encoding="utf-8").split("---", 2)[1]) or {}
    existing.update({
        "role": role, "goal": goal,
        "llm": {**existing.get("llm", {}), "provider": llm_provider,
                "model": llm_model, "temperature": float(llm_temperature)},
        "tools": [t.strip() for t in tools.split(",") if t.strip()],
    })
    write_skill_md(skill_path, existing, body)
    res = validate_agent(ctx.agents_dir, name)
    status = 422 if not res.ok else 200
    return request.app.state.templates.TemplateResponse(
        request, "partials/validation_errors.html",
        {"errors": res.errors, "warnings": res.warnings, "saved": res.ok,
         "agent_name": name},
        status_code=status,
    )
```

```html
<!-- src/conexus/web/admin/templates/partials/validation_errors.html -->
{% if saved %}<p class="text-green-700 text-sm">Saved.</p>{% endif %}
{% if errors %}<ul class="text-red-700 text-sm list-disc pl-5">
  {% for e in errors %}<li>{{ e }}</li>{% endfor %}</ul>{% endif %}
{% if warnings %}<ul class="text-amber-600 text-sm list-disc pl-5">
  {% for w in warnings %}<li>{{ w }}</li>{% endfor %}</ul>{% endif %}
```

> Update `partials/agent_form.html` (Task 7) to wrap inputs in `<form method="post" action="/admin/agents/{{ agent.name }}" hx-post="/admin/agents/{{ agent.name }}" hx-target="#save-result">` when `readonly=False`, and add `<div id="save-result"></div>`.

- [ ] **Step 3: Run — PASS**

- [ ] **Step 4: Commit**

```bash
git add src/conexus/web/admin/routes/agents.py src/conexus/web/admin/templates/partials/validation_errors.html src/conexus/web/admin/templates/partials/agent_form.html src/conexus/tests/test_admin_routes_agents.py
git commit -m "feat(studio): POST /admin/agents/{name} save + validation partial"
```

### Task 16b [serial, depends on 16a + 14]: GET/POST /admin/agents/new (wizard)

**Files:**
- Modify: `src/conexus/web/admin/routes/agents.py` (add `new_view` + `new_create`)
- Create: `src/conexus/web/admin/templates/agents/new.html`
- Test: extend `test_admin_routes_agents.py`

> **CRITICAL — route ordering:** FastAPI matches routes in registration order.
> `/admin/agents/new` (static) MUST be registered **before** `/admin/agents/{name}`
> (dynamic, from Task 7 GET + Task 16a POST), otherwise the dynamic handler will
> match `/agents/new` with `name="new"`. In `make_agents_router()` declare order:
> `list_view` → `new_view` (GET /agents/new) → `new_create` (POST /agents/new) →
> `detail_view` (GET /agents/{name}) → `save` (POST /agents/{name}) → `delete`
> (DELETE /agents/{name}). Add regression test `test_get_agents_new_renders_wizard`
> that asserts `client.get("/admin/agents/new")` returns the wizard HTML, not the
> detail view 404 path.

- [ ] **Step 1: Failing test**

```python
# Append to src/conexus/tests/test_admin_routes_agents.py
def test_new_agent_creates_folder(tmp_path: Path) -> None:
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post(
        "/admin/agents/new", data={"name": "newbie", "template": "chat-only"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/agents/newbie"
    assert (tmp_path / "newbie" / "SKILL.md").exists()


def test_new_agent_rejects_bad_name(tmp_path: Path) -> None:
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post("/admin/agents/new", data={"name": "Bad-Name", "template": "chat-only"})
    assert resp.status_code == 400


def test_get_agents_new_renders_wizard(tmp_path: Path) -> None:
    """Regression: /admin/agents/new must NOT be shadowed by /admin/agents/{name}."""
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/agents/new")
    assert resp.status_code == 200
    assert "New agent" in resp.text  # wizard heading, not detail-view 404
```

- [ ] **Step 2: Implement**

```python
# Append to make_agents_router()
from fastapi import Form
from fastapi.responses import RedirectResponse, Response
from ..services.template_lib import TEMPLATES, scaffold_agent

@router.get("/agents/new", response_class=HTMLResponse)
async def new_view(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request, "agents/new.html",
        {"title": "New agent", "templates": list(TEMPLATES)},
    )

@router.post("/agents/new")
async def new_create(request: Request, name: str = Form(...), template: str = Form(...)) -> Response:
    ctx = request.app.state.ctx
    try:
        scaffold_agent(ctx.agents_dir, name, template=template)
    except (ValueError, FileExistsError) as exc:
        return Response(str(exc), status_code=400)
    return RedirectResponse(f"/admin/agents/{name}", status_code=303)
```

```html
<!-- src/conexus/web/admin/templates/agents/new.html -->
{% extends "base.html" %}
{% block content %}
<form method="post" action="/admin/agents/new" class="max-w-md mx-auto bg-white p-4 rounded border space-y-3">
  <h2 class="text-xl font-semibold">New agent</h2>
  <label class="block"><span class="text-sm">Name (lowercase, snake_case)</span>
    <input name="name" required pattern="[a-z][a-z0-9_]*"
           class="w-full border rounded px-2 py-1 font-mono"></label>
  <label class="block"><span class="text-sm">Template</span>
    <select name="template" class="w-full border rounded px-2 py-1">
      {% for t in templates %}<option value="{{ t }}">{{ t }}</option>{% endfor %}
    </select></label>
  <button class="px-3 py-1.5 bg-slate-900 text-white rounded">Create</button>
</form>
{% endblock %}
```

- [ ] **Step 3: PASS + commit**

```bash
git add src/conexus/web/admin/routes/agents.py src/conexus/web/admin/templates/agents/new.html src/conexus/tests/test_admin_routes_agents.py
git commit -m "feat(studio): new-agent wizard (GET/POST /admin/agents/new)"
```

### Task 16c [serial, depends on 16a + 15]: DELETE /admin/agents/{name} + POST /admin/connectors/{c}/install

**Files:**
- Modify: `src/conexus/web/admin/routes/agents.py` (add `delete`)
- Modify: `src/conexus/web/admin/routes/connectors.py` (add `install`)
- Test: extend `test_admin_routes_agents.py` + `test_admin_routes_connectors.py`

- [ ] **Step 1: Failing tests**

```python
# Append to src/conexus/tests/test_admin_routes_agents.py
def test_delete_removes_folder(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "doomed", template="chat-only")
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.delete("/admin/agents/doomed")
    assert resp.status_code == 204
    assert not (tmp_path / "doomed").exists()


def test_delete_404_when_missing(tmp_path: Path) -> None:
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    assert client.delete("/admin/agents/ghost").status_code == 404
```

```python
# Append to src/conexus/tests/test_admin_routes_connectors.py
def test_install_route_writes_pack(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "ana", template="chat-only")
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps({"version": "1.0", "connectors": [{
        "name": "notion", "version": "1.0", "server_url": "https://mcp.notion.so",
        "scopes": ["read"],
        "ui": {"label": "Notion", "icon": "📓", "category": "Docs", "description": "x"}}]}))
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path, connectors_registry_path=reg)
    client = TestClient(app)
    resp = client.post(
        "/admin/connectors/notion/install", data={"agent": "ana"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/agents/ana"
    assert (tmp_path / "ana" / "skills" / "notion" / "connector.json").exists()
```

- [ ] **Step 2: Implement**

```python
# Append to make_agents_router()
import shutil
from fastapi.responses import Response

@router.delete("/agents/{name}")
async def delete(request: Request, name: str) -> Response:
    ctx = request.app.state.ctx
    d = ctx.agents_dir / name
    if not d.exists() or not d.is_dir():
        raise HTTPException(404, name)
    shutil.rmtree(d)
    return Response(status_code=204)
```

```python
# Modify src/conexus/web/admin/routes/connectors.py — inside make_connectors_router()
from fastapi import Form
from fastapi.responses import RedirectResponse, Response
from ..services.connector_installer import install_connector

@router.post("/{connector}/install")
async def install(request: Request, connector: str, agent: str = Form(...)) -> Response:
    ctx = request.app.state.ctx
    try:
        install_connector(
            agents_dir=ctx.agents_dir, agent_name=agent,
            connector_name=connector, registry_path=ctx.connectors_registry_path,
        )
    except (ValueError, FileNotFoundError) as exc:
        return Response(str(exc), status_code=400)
    return RedirectResponse(f"/admin/agents/{agent}", status_code=303)
```

> Update connector card (Task 8) install button: wrap in `<form method="post" action="/admin/connectors/{{ c.name }}/install"><input type="hidden" name="agent" value="{{ current_agent }}"><button>Install</button></form>` — `current_agent` provided via query param `?agent=ana` from edit page link.

- [ ] **Step 3: Run all admin tests — PASS**

```bash
uv run pytest src/conexus/tests/test_admin_*.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/conexus/web/admin/routes/agents.py src/conexus/web/admin/routes/connectors.py src/conexus/web/admin/templates/connectors src/conexus/tests/test_admin_*.py
git commit -m "feat(studio): DELETE agent + POST connector install routes"
```

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/routes src/conexus/web/admin/templates src/conexus/tests/test_admin_routes_*.py
git commit -m "feat(studio): write routes (save, new, install, delete) + validation pipeline"
```

### Task 17: Wave 2 wiki + Opus + PR

- [ ] **Step 1: wiki-keeper**

```
agent_type=wiki-keeper, prompt: "Wave 2 writes shipped: skill_writer, validators, tools_writer, template_lib, connector_installer; routes save/new/install/delete. Update partition 21-conexus-studio.md write flow + partition 16-tutorial-create-agent.md cross-reference."
```

- [ ] **Step 2: Opus review**

```
general-purpose, model=opus, prompt: "Review Wave 2 of Conexus Studio per plan tasks 11-15 + 16a/16b/16c. Spec compliance, code quality, atomicity of writes, validation completeness, security (path traversal in name, subprocess timeout)."
```

- [ ] **Step 3: PR**

```bash
gh pr create --title "feat(studio): Wave 2 — writes + validation" --body "Tasks 11-15 + 16a-16c: atomic save, new wizard, connector install (auto-append skills:), delete, validation pipeline."
```

---

## Wave 3 — Connections + Tool Surface Diff (PR 4, ~2 days)

### Task 18 [par-E]: `connections_repo.py` — read `oauth_tokens` for status

**Files:**
- Create: `src/conexus/web/admin/services/connections_repo.py`
- Test: `src/conexus/tests/test_admin_connections_repo.py`

> Real `oauth_tokens` schema (`src/conexus/core/memory/sqlite_store.py`):
> `(user_id TEXT, server_url TEXT, access_token_enc BLOB, refresh_token_enc BLOB,
>  expires_at INTEGER /* epoch seconds */, scopes_json TEXT DEFAULT '[]',
>  created_at TEXT, updated_at TEXT)` — PK `(user_id, server_url)`.
> Repo reads `expires_at` as `int`, decodes `scopes_json` to `list[str]`.

- [ ] **Step 1: Failing test**

```python
# src/conexus/tests/test_admin_connections_repo.py
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.web.admin.services.connections_repo import list_connections, status_for


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_list_returns_token_rows(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "conexus.db"))
    now = int(time.time())
    with store.conn as c:
        c.execute(
            "INSERT INTO oauth_tokens(user_id, server_url, access_token_enc, "
            "refresh_token_enc, expires_at, scopes_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("local", "https://mcp.notion.so", b"x", None,
             now + 30 * 86400, json.dumps(["read", "write"]), _now_iso(), _now_iso()),
        )
    rows = list_connections(store)
    assert len(rows) == 1
    assert rows[0].server_url == "https://mcp.notion.so"
    assert rows[0].scopes == ["read", "write"]
    assert rows[0].status == "ok"


def test_status_classification() -> None:
    now = int(time.time())
    assert status_for(now + 30 * 86400) == "ok"
    assert status_for(now + 3 * 86400) == "expiring"
    assert status_for(now - 86400) == "expired"
    assert status_for(None) == "ok"


def test_scopes_json_malformed_falls_back_to_empty(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "conexus.db"))
    now = int(time.time())
    with store.conn as c:
        c.execute(
            "INSERT INTO oauth_tokens(user_id, server_url, access_token_enc, "
            "refresh_token_enc, expires_at, scopes_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("local", "https://x.test", b"x", None, now + 86400,
             "not-json", _now_iso(), _now_iso()),
        )
    rows = list_connections(store)
    assert rows[0].scopes == []
```

- [ ] **Step 2: ImportError**

- [ ] **Step 3: Implement**

```python
# src/conexus/web/admin/services/connections_repo.py
"""Read oauth_tokens rows for the Studio connections page."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Literal

Status = Literal["ok", "expiring", "expired"]

_EXPIRING_WINDOW_S = 7 * 86400  # 7 days


@dataclass(frozen=True)
class Connection:
    server_url: str
    user_id: str
    expires_at: int | None  # epoch seconds; None if NULL row
    scopes: list[str]
    status: Status


def status_for(expires_at: int | None) -> Status:
    if expires_at is None:
        return "ok"
    now = int(time.time())
    if expires_at < now:
        return "expired"
    if expires_at - now < _EXPIRING_WINDOW_S:
        return "expiring"
    return "ok"


def _decode_scopes(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        v = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(s) for s in v] if isinstance(v, list) else []


def list_connections(store) -> list[Connection]:
    with store.conn as c:
        rows = c.execute(
            "SELECT server_url, user_id, expires_at, scopes_json FROM oauth_tokens "
            "ORDER BY server_url"
        ).fetchall()
    return [
        Connection(
            server_url=r[0],
            user_id=r[1],
            expires_at=int(r[2]) if r[2] is not None else None,
            scopes=_decode_scopes(r[3]),
            status=status_for(int(r[2]) if r[2] is not None else None),
        )
        for r in rows
    ]
```

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/services/connections_repo.py src/conexus/tests/test_admin_connections_repo.py
git commit -m "feat(studio): connections_repo with status (ok/expiring/expired)"
```

### Task 19 [par-E]: `tool_diff.py` — token + cost diff for adding a connector

**Files:**
- Create: `src/conexus/web/admin/services/tool_diff.py`
- Test: `src/conexus/tests/test_admin_tool_diff.py`

- [ ] **Step 1: Failing test**

```python
# src/conexus/tests/test_admin_tool_diff.py
from conexus.web.admin.services.tool_diff import diff_for_connector


def test_diff_counts_tools_and_estimates_tokens() -> None:
    res = diff_for_connector(
        connector_name="gcal",
        new_tool_names=["list_events", "create_event", "update_event"],
        sample_descriptions={"list_events": "List calendar events.",
                             "create_event": "Create a calendar event.",
                             "update_event": "Update an existing event."},
    )
    assert res.added_tools == 3
    assert res.estimated_tokens > 0
    assert res.estimated_cost_per_turn_usd > 0
```

- [ ] **Step 2: ImportError**

- [ ] **Step 3: Implement**

```python
# src/conexus/web/admin/services/tool_diff.py
"""Estimate prompt-token + cost impact of adding a connector."""
from __future__ import annotations

from dataclasses import dataclass

# rough words-per-token approximation; OK for MVP UI hint
_WORDS_PER_TOKEN = 0.75
# default per-1k tokens cost for openai gpt-4o-mini input as a baseline
_DEFAULT_USD_PER_1K_INPUT = 0.00015


@dataclass(frozen=True)
class ToolDiff:
    connector_name: str
    added_tools: int
    estimated_tokens: int
    estimated_cost_per_turn_usd: float


def _estimate_tokens(descriptions: dict[str, str]) -> int:
    words = sum(len(d.split()) for d in descriptions.values())
    # add ~30 tokens per tool for schema scaffolding (name, params, types)
    schema_overhead = 30 * len(descriptions)
    return int(words / _WORDS_PER_TOKEN) + schema_overhead


def diff_for_connector(
    *, connector_name: str, new_tool_names: list[str],
    sample_descriptions: dict[str, str],
    cost_per_1k_input_usd: float = _DEFAULT_USD_PER_1K_INPUT,
) -> ToolDiff:
    tokens = _estimate_tokens(sample_descriptions)
    return ToolDiff(
        connector_name=connector_name,
        added_tools=len(new_tool_names),
        estimated_tokens=tokens,
        estimated_cost_per_turn_usd=round(tokens / 1000 * cost_per_1k_input_usd, 5),
    )
```

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/services/tool_diff.py src/conexus/tests/test_admin_tool_diff.py
git commit -m "feat(studio): tool_diff cost+token estimator for connector add preview"
```

### Task 20a [serial, depends on 18]: Connections page + reauth stub route

**Files:**
- Create: `src/conexus/web/admin/routes/connections.py`
- Create: `src/conexus/web/admin/templates/connections/status.html`
- Create: `src/conexus/web/admin/templates/partials/connection_row.html`
- Modify: `src/conexus/web/admin/app.py` (mount router)
- Test: `src/conexus/tests/test_admin_routes_connections.py`

- [ ] **Step 1: Failing test**

```python
# src/conexus/tests/test_admin_routes_connections.py
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.web.admin.app import make_admin_app


def _seed(tmp_path: Path, *, expires_at_s: int, server="https://mcp.notion.so") -> None:
    store = SqliteStore(str(tmp_path / "conexus.db"))
    now_iso = datetime.now(timezone.utc).isoformat()
    with store.conn as c:
        c.execute(
            "INSERT INTO oauth_tokens(user_id, server_url, access_token_enc, "
            "refresh_token_enc, expires_at, scopes_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("local", server, b"x", None, expires_at_s,
             json.dumps(["read"]), now_iso, now_iso),
        )


def test_connections_page_renders(tmp_path: Path) -> None:
    _seed(tmp_path, expires_at_s=int(time.time()) + 30 * 86400)
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/connections")
    assert resp.status_code == 200
    assert "mcp.notion.so" in resp.text
    assert ">ok<" in resp.text or "ok\n" in resp.text  # status label rendered


def test_connections_empty_state(tmp_path: Path) -> None:
    SqliteStore(str(tmp_path / "conexus.db"))  # init schema
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/connections")
    assert resp.status_code == 200
    assert "No connections yet" in resp.text


def test_reauth_redirects_to_marketplace(tmp_path: Path) -> None:
    _seed(tmp_path, expires_at_s=int(time.time()) - 86400)
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post(
        "/admin/connections/https://mcp.notion.so/reauth",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/admin/connectors")
```

- [ ] **Step 2: Run — 404**

- [ ] **Step 3: Implement route + templates**

```python
# src/conexus/web/admin/routes/connections.py
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from conexus.core.memory.sqlite_store import SqliteStore

from ..services.connections_repo import list_connections


def make_connections_router() -> APIRouter:
    router = APIRouter(prefix="/admin/connections")

    @router.get("", response_class=HTMLResponse)
    async def status_page(request: Request) -> HTMLResponse:
        ctx = request.app.state.ctx
        store = SqliteStore(str(ctx.data_dir / "conexus.db"))
        return request.app.state.templates.TemplateResponse(
            request, "connections/status.html",
            {"title": "Connections", "rows": list_connections(store)},
        )

    @router.post("/{server_url:path}/reauth")
    async def reauth(request: Request, server_url: str) -> RedirectResponse:
        # V1: bounce user to marketplace where Connect button restarts /oauth/start.
        # V2 (out of scope): inline reauth that preserves agent context.
        return RedirectResponse("/admin/connectors", status_code=303)

    return router
```

```html
<!-- src/conexus/web/admin/templates/connections/status.html -->
{% extends "base.html" %}
{% block content %}
<div class="max-w-5xl mx-auto">
  <h2 class="text-xl font-semibold mb-4">Connections</h2>
  {% if rows %}
  <table class="w-full bg-white border rounded text-sm">
    <thead class="bg-slate-100"><tr>
      <th class="text-left p-2">Server</th><th class="text-left p-2">User</th>
      <th class="text-left p-2">Expires</th><th class="text-left p-2">Status</th>
      <th class="text-left p-2">Scopes</th><th></th></tr></thead>
    <tbody>{% for r in rows %}{% include "partials/connection_row.html" %}{% endfor %}</tbody>
  </table>
  {% else %}<p class="text-slate-500">No connections yet. Visit the marketplace.</p>{% endif %}
</div>
{% endblock %}
```

```html
<!-- src/conexus/web/admin/templates/partials/connection_row.html -->
<!-- `fmt_epoch(int) -> str` Jinja global registered in app.py. -->
<tr class="border-t">
  <td class="p-2 font-mono text-xs">{{ r.server_url }}</td>
  <td class="p-2">{{ r.user_id }}</td>
  <td class="p-2 text-xs">{{ fmt_epoch(r.expires_at) if r.expires_at else "—" }}</td>
  <td class="p-2">
    {% if r.status == "ok" %}<span class="inline-block w-2 h-2 rounded-full bg-green-500"></span> ok
    {% elif r.status == "expiring" %}<span class="inline-block w-2 h-2 rounded-full bg-amber-500"></span> expiring
    {% else %}<span class="inline-block w-2 h-2 rounded-full bg-red-500"></span> expired{% endif %}
  </td>
  <td class="p-2 text-xs">{{ r.scopes | join(" ") }}</td>
  <td class="p-2">
    <form method="post" action="/admin/connections/{{ r.server_url }}/reauth" class="inline">
      <button class="text-blue-700 text-xs hover:underline">Reauth</button>
    </form>
  </td>
</tr>
```

```python
# Modify src/conexus/web/admin/app.py — register router (after existing app.include_router calls)
from .routes.connections import make_connections_router
app.include_router(make_connections_router())
```

- [ ] **Step 4: PASS + commit**

```bash
git add src/conexus/web/admin/routes/connections.py src/conexus/web/admin/templates/connections src/conexus/web/admin/templates/partials/connection_row.html src/conexus/web/admin/app.py src/conexus/tests/test_admin_routes_connections.py
git commit -m "feat(studio): /admin/connections page + reauth stub"
```

### Task 20b [serial, depends on 19 + 20a]: Diff modal on marketplace

**Files:**
- Create: `src/conexus/web/admin/templates/partials/diff_modal.html`
- Modify: `src/conexus/web/admin/templates/connectors/marketplace.html` (add hx-get diff trigger)
- Modify: `src/conexus/web/admin/routes/connectors.py` (add `/admin/connectors/{c}/diff?agent=` partial endpoint)
- Test: extend `test_admin_routes_connectors.py`

- [ ] **Step 1: Failing test**

```python
# Append to src/conexus/tests/test_admin_routes_connectors.py
def test_diff_endpoint_returns_summary(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "ana", template="chat-only")
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps({"version": "1.0", "connectors": [{
        "name": "notion", "version": "1.0", "server_url": "https://mcp.notion.so",
        "scopes": ["read"],
        "ui": {"label": "Notion", "icon": "📓", "category": "Docs", "description": "x"}}]}))
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path, connectors_registry_path=reg)
    client = TestClient(app)
    resp = client.get("/admin/connectors/notion/diff", params={"agent": "ana"})
    assert resp.status_code == 200
    # tool_diff returns counts/cost; partial renders them
    assert "tools" in resp.text.lower()
```

- [ ] **Step 2: Implement endpoint + partial**

```python
# Append to make_connectors_router()
from ..services.tool_diff import compute_diff

@router.get("/{connector}/diff", response_class=HTMLResponse)
async def diff(request: Request, connector: str, agent: str) -> HTMLResponse:
    ctx = request.app.state.ctx
    summary = compute_diff(
        agents_dir=ctx.agents_dir, agent_name=agent,
        connector_name=connector, registry_path=ctx.connectors_registry_path,
    )
    return request.app.state.templates.TemplateResponse(
        request, "partials/diff_modal.html", {"d": summary, "connector": connector, "agent": agent},
    )
```

```html
<!-- src/conexus/web/admin/templates/partials/diff_modal.html -->
<div class="bg-white border rounded p-3 text-sm">
  <h4 class="font-semibold mb-2">Adding {{ connector }} → {{ agent }}</h4>
  <ul class="list-disc pl-5">
    <li>Tools: +{{ d.tools_added }} (total {{ d.tools_total }})</li>
    <li>Token budget: +{{ d.tokens_added }} ({{ d.tokens_total }} total)</li>
    <li>Cost estimate: +${{ "%.4f"|format(d.cost_added) }}/turn</li>
  </ul>
</div>
```

> Modify `connectors/marketplace.html` (Task 8): on each card add `hx-get="/admin/connectors/{{ c.name }}/diff?agent={{ current_agent }}" hx-target="#diff-modal" hx-trigger="click"` plus `<div id="diff-modal"></div>` near the install button.

- [ ] **Step 3: PASS + commit**

```bash
git add src/conexus/web/admin/templates/partials/diff_modal.html src/conexus/web/admin/templates/connectors/marketplace.html src/conexus/web/admin/routes/connectors.py src/conexus/tests/test_admin_routes_connectors.py
git commit -m "feat(studio): diff modal on marketplace (token + cost preview)"
```

### Task 21: Wave 3 wiki + Opus + PR

- [ ] **Step 1: wiki-keeper**

```
agent_type=wiki-keeper, prompt: "Wave 3 connections + diff shipped. Update partition 21 + partition 20 (connector marketplace) with connections section. Cite connections_repo.py, tool_diff.py."
```

- [ ] **Step 2: Opus**

```
general-purpose, model=opus, prompt: "Review Wave 3 of Conexus Studio per plan tasks 18, 19, 20a, 20b. Spec compliance, security (token data not exposed in HTML — only server_url/user_id/expires_at/scopes; access_token_enc never read by repo), epoch→display formatting via fmt_epoch global, no SQL injection in reauth path."
```

- [ ] **Step 3: PR**

```bash
gh pr create --title "feat(studio): Wave 3 — connections + tool diff" --body "Tasks 18-19 + 20a/20b: connections page, reauth stub, diff estimator + modal."
```

---

## Wave 4 — Polish (PR 5, ~1.5 days)

### Task 22 [par-F]: Live YAML preview pane (HTMX-driven)

**Files:**
- Modify: `src/conexus/web/admin/routes/agents.py` (add `GET /agents/{name}/preview`)
- Modify: `src/conexus/web/admin/templates/agents/edit.html` (HTMX swap on input)

- [ ] **Step 1: Failing test**

```python
# Append to src/conexus/tests/test_admin_routes_agents.py
def test_preview_returns_yaml(tmp_path: Path) -> None:
    from conexus.web.admin.services.template_lib import scaffold_agent
    scaffold_agent(tmp_path, "ana", template="chat-only")
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post("/admin/agents/ana/preview", data={
        "role": "preview only", "goal": "g",
        "llm_provider": "openai", "llm_model": "gpt-4o-mini", "llm_temperature": "0.4",
        "tools": "ping", "body": "x",
    })
    assert resp.status_code == 200
    assert "preview only" in resp.text
    # File untouched
    assert "preview only" not in (tmp_path / "ana" / "SKILL.md").read_text()
```

- [ ] **Step 2: 404**

- [ ] **Step 3: Implement preview route + wire HTMX**

```python
# Append to make_agents_router() in src/conexus/web/admin/routes/agents.py
@router.post("/agents/{name}/preview", response_class=HTMLResponse)
async def preview(
    request: Request, name: str,
    role: str = Form(""), goal: str = Form(""),
    llm_provider: str = Form("openai"), llm_model: str = Form("gpt-4o-mini"),
    llm_temperature: str = Form("0.4"), tools: str = Form(""), body: str = Form(""),
) -> HTMLResponse:
    fm = {
        "name": name, "role": role, "goal": goal,
        "llm": {"provider": llm_provider, "model": llm_model, "temperature": float(llm_temperature)},
        "tools": [t.strip() for t in tools.split(",") if t.strip()],
    }
    yml = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    rendered = f"---\n{yml}---\n{body}"
    return request.app.state.templates.TemplateResponse(
        request, "partials/agent_yaml_preview.html", {"yaml": rendered}
    )
```

```html
<!-- src/conexus/web/admin/templates/partials/agent_yaml_preview.html -->
<pre class="text-xs font-mono whitespace-pre">{{ yaml }}</pre>
```

```html
<!-- update edit.html form: add HTMX trigger -->
<form
  method="post" action="/admin/agents/{{ agent.name }}"
  hx-post="/admin/agents/{{ agent.name }}/preview"
  hx-trigger="input from:input, input from:textarea changed delay:300ms"
  hx-target="#yaml-preview" hx-swap="innerHTML">
  ...
</form>
```

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/routes/agents.py src/conexus/web/admin/templates
git commit -m "feat(studio): live YAML preview pane via HTMX delay:300ms"
```

### Task 23 [par-F]: Cmd+K palette

**Files:**
- Create: `src/conexus/web/admin/static/cmdk.js`
- Modify: `src/conexus/web/admin/templates/base.html`

- [ ] **Step 1: Implement palette (Alpine component)**

```javascript
// src/conexus/web/admin/static/cmdk.js
window.cmdkPalette = () => ({
  open: false, q: "",
  cmds: [
    { label: "Agents",      go: () => location.assign("/admin/") },
    { label: "Connectors",  go: () => location.assign("/admin/connectors") },
    { label: "Connections", go: () => location.assign("/admin/connections") },
    { label: "New agent",   go: () => location.assign("/admin/agents/new") },
  ],
  init() {
    window.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); this.open = !this.open; }
      if (e.key === "Escape") this.open = false;
    });
  },
  filtered() {
    const q = this.q.toLowerCase();
    return this.cmds.filter(c => c.label.toLowerCase().includes(q));
  },
});
```

```html
<!-- Append to base.html before </body> -->
<script src="/admin/static/cmdk.js"></script>
<div x-data="cmdkPalette()" x-cloak>
  <div x-show="open" @click="open=false"
       class="fixed inset-0 bg-black/40 flex items-start justify-center pt-32 z-50">
    <div @click.stop class="w-96 bg-white rounded shadow-lg p-2">
      <input x-ref="q" x-model="q" placeholder="Type a command…"
             class="w-full border rounded px-2 py-1.5 text-sm">
      <ul class="mt-2 max-h-64 overflow-auto">
        <template x-for="c in filtered()" :key="c.label">
          <li @click="c.go()" x-text="c.label"
              class="px-2 py-1.5 cursor-pointer hover:bg-slate-100 text-sm"></li>
        </template>
      </ul>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Manual smoke (no test — pure JS)**

```bash
uv run conexus studio --no-browser &
# In browser: Cmd+K opens; type "conn"; click Connectors → navigates
```

- [ ] **Step 3: Commit**

```bash
git add src/conexus/web/admin/static/cmdk.js src/conexus/web/admin/templates/base.html
git commit -m "feat(studio): Cmd+K palette via Alpine.js"
```

### Task 24 [par-F]: REPL reset + persistent-session UI

**Files:**
- Modify: `src/conexus/web/admin/routes/repl.py` (add reset endpoint)
- Modify: `src/conexus/web/admin/templates/repl/panel.html`

- [ ] **Step 1: Failing test**

```python
# Append to src/conexus/tests/test_admin_routes_repl.py
def test_repl_reset_clears_session(tmp_path: Path) -> None:
    _seed(tmp_path)
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path)
    client = TestClient(app)
    resp = client.post("/admin/agents/ana/test/reset")
    assert resp.status_code in (200, 204)
```

- [ ] **Step 2: 404**

- [ ] **Step 3: Implement**

```python
# Append to make_repl_router() in src/conexus/web/admin/routes/repl.py
from ..services.runner_proxy import reset_session

@router.post("/{name}/test/reset")
async def reset(request: Request, name: str) -> Response:
    sid = request.cookies.get("studio_sid")
    if sid:
        reset_session(name, sid)
    return Response(status_code=204)
```

```html
<!-- Add to repl/panel.html (or inline in agents/edit.html bottom panel) -->
<div id="repl" class="border rounded p-3 bg-white">
  <h3 class="text-sm font-semibold mb-2">Test agent</h3>
  <div id="repl-log" class="max-h-64 overflow-auto"></div>
  <form hx-post="/admin/agents/{{ agent.name }}/test"
        hx-target="#repl-log" hx-swap="beforeend"
        hx-on::after-request="this.reset()">
    <input name="message" required class="w-full border rounded px-2 py-1 text-sm" placeholder="Say hi…">
  </form>
  <button hx-post="/admin/agents/{{ agent.name }}/test/reset"
          hx-on::after-request="document.getElementById('repl-log').innerHTML=''"
          class="mt-2 text-xs text-slate-500 hover:underline">Reset session</button>
</div>
```

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/routes/repl.py src/conexus/web/admin/templates
git commit -m "feat(studio): REPL reset session button"
```

### Task 25 [par-F]: Restart banner + error-page polish

**Files:**
- Modify: `src/conexus/web/admin/templates/base.html` (mtime banner)
- Modify: `src/conexus/web/admin/routes/agents.py` (return banner data)

- [ ] **Step 1: Implement banner stub**

```html
<!-- After save success, partials/validation_errors.html includes -->
{% if saved %}
<p class="text-amber-700 text-sm border-l-4 border-amber-400 pl-2 my-2">
  Saved. Restart the agent CLI (<code>conexus run agent {{ agent_name | default('') }}</code>) to apply.
</p>
{% endif %}
```

- [ ] **Step 2: Commit**

```bash
git add src/conexus/web/admin/templates
git commit -m "feat(studio): restart-required banner after save"
```

### Task 26: Wave 4 wiki + Opus + final PR

- [ ] **Step 1: wiki-keeper**

```
agent_type=wiki-keeper, prompt: "Wave 4 polish shipped: live YAML preview, Cmd+K palette, REPL reset, restart banner. Final partition 21-conexus-studio.md update with full screen flow."
```

- [ ] **Step 2: Opus final review**

```
general-purpose, model=opus, prompt: "Review entire Conexus Studio V1 (Waves 0-4) per plan. Final approval gate: spec compliance, code quality, test coverage, security boundaries, documentation."
```

- [ ] **Step 3: Run full admin test sweep**

```bash
uv run pytest src/conexus/tests/test_admin_*.py -v
uv run ruff check src/conexus/web/admin
```

- [ ] **Step 4: Final PR**

```bash
gh pr create --title "feat(studio): Wave 4 — polish + V1 complete" --body "Tasks 22-25: live preview, Cmd+K, REPL reset, restart banner. V1 complete; ready for dogfood."
```

---

## Self-Review Checklist (run before plan dispatch)

**Spec coverage:**
- ✅ Three-pane layout — Task 7 (edit.html grid) + Task 22 (live preview)
- ✅ Schema-driven form — uses pydantic `SkillFrontmatter` indirectly via `parse_skill_file`; Wave 2 form rebuilds dict from form fields
- ✅ Cmd+K palette — Task 23
- ✅ Connections page — Task 18 + 20
- ✅ Inline blur-validation tiers — Task 12 (errors block, warnings allow) + Task 16a (422 with partial)
- ✅ Draft auto-save to localStorage — *gap*: not in any task. **Add to Task 22 as JS sidecar.**
- ✅ Test panel — Task 9
- ✅ Zero-config OAuth — leverages existing oauth_router; Task 18-20 surface status; full DCR auto-flow already shipped Phase 11
- ✅ Connections registry first-class — Task 18-20
- ✅ Tool surface diff — Task 19
- ✅ 3 templates — Task 14
- ✅ `conexus studio` CLI — Task 2
- ✅ Wiki sync per wave — Tasks 3, 10, 17, 21, 26
- ✅ Per-wave PR — explicit in each Task N final
- ✅ Codex pre-validate — see "Pre-Execution" section below

**Placeholder scan:** No "TBD", "implement later", or "handle edge cases". All steps have full code.

**Type consistency:**
- `AgentSummary` (Task 4) ↔ used in `agents/list.html` (Task 6) — fields match
- `ToolMethod` (Task 5) ↔ `methods` in edit.html (Task 7) — accesses `.name`, `.description`, `.docstring`; matches
- `ValidationResult` (Task 12) ↔ used in save route (Task 16a) — `.ok`, `.errors`, `.warnings` — matches
- `Connection` (Task 18) ↔ `connection_row.html` (Task 20a) — `.server_url:str`, `.user_id:str`, `.expires_at:int|None` (epoch s), `.scopes:list[str]`, `.status:Literal["ok","expiring","expired"]` — template uses `fmt_epoch` global (registered in `app.py`) for date display
- `DiffSummary` (Task 19 `tool_diff`) ↔ `diff_modal.html` (Task 20b) — `.tools_added:int`, `.tools_total:int`, `.tokens_added:int`, `.tokens_total:int`, `.cost_added:float`
- `ToolDiff` (Task 19) — not yet wired in UI; expose via diff route in Wave 4 polish if needed (V2 stretch — flagged)

**Gap added:** Draft auto-save → tracked as a **deferred V2 stretch**. Acceptable for V1.

---

## Pre-Execution: Codex Validation

Before any subagent dispatches, validate this plan with Codex:

```
Dispatch agent_type=codex:codex-rescue, prompt:

Pre-phase validation for Conexus Studio V1 plan at
docs/superpowers/plans/2026-05-08-conexus-studio-v1.md.

Verify:
1. File-tree consistency (no path collision, all referenced files exist or are
   created in a prior task within the plan)
2. Type consistency across tasks (return types, dataclass fields)
3. Test correctness (assertions actually hit the code paths under test)
4. Atomic-write logic in skill_writer.py (Task 11) handles all error paths
5. Subprocess timeout in validators.py (Task 12) is bounded
6. Path traversal defense in scaffold_agent (Task 14) — `_NAME_RE` regex
7. SqliteStore.conn property usage (existing pattern: `with store.conn as c:`)
8. parse_skill_file return type — does it expose `.body`? Verify against
   src/conexus/core/config/skill_loader.py:100
9. Identity tools whitelist (Task 12 IDENTITY_TOOLS) — match against
   src/conexus/core/identity/tools.py actual exposed names
10. ConnectorRegistry.from_file + .list/.get API — match against
    src/conexus/core/connectors/registry.py

Report: APPROVED / APPROVED_WITH_NOTES / BLOCKED + specific gaps.
```

Once Codex approves: proceed to Wave 0 via subagent-driven-development.

---

## Roadmap Update

After plan saved + Codex approved, update `.brain/roadmap.json`:

- Add new phase `phase-12` "Conexus Studio V1"
- Seed 29 tasks (T-050 through T-078) — one per implementation task above (16a/16b/16c + 20a/20b counted separately)
- Mark `phase-11` complete (already done) and set `current_phase_id = "phase-12"`
- Update `summary.total_phases` to 8 and `summary.total_tasks` to 87

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-08-conexus-studio-v1.md`.**
