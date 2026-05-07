# 21 — Conexus Studio

Local web UI for Conexus. Shipped in Phase 12 Wave 0 as a FastAPI sub-app
mounted at `/admin/` and launched via the `conexus studio` CLI subcommand.
Wave 0 is a scaffold: routing skeleton, dependency-injection context, and
front-end wiring. No business-logic views exist yet.

---

## 1. Executive summary

Studio gives operators a browser-based control plane without touching Telegram
or the SQLite shell. The server is intentionally localhost-only (`127.0.0.1`);
there is no auth layer in Wave 0.

Key modules:

| Module | Path |
|--------|------|
| App factory | `src/conexus/web/admin/app.py` |
| AdminContext (DI dataclass) | `src/conexus/web/admin/deps.py` |
| Base Jinja2 template | `src/conexus/web/admin/templates/base.html` |
| Static assets | `src/conexus/web/admin/static/app.css` |
| Route package (empty scaffold) | `src/conexus/web/admin/routes/__init__.py` |
| Service package (empty scaffold) | `src/conexus/web/admin/services/__init__.py` |
| CLI subcommand | `src/conexus/cli/__main__.py` (`_handle_studio`, `_build_parser`) |

---

## 2. App factory

`make_admin_app` in `src/conexus/web/admin/app.py:28` is the sole public
surface of the package. Signature:

```python
def make_admin_app(
    *,
    agents_dir: Path,
    data_dir: Path,
    connectors_registry_path: Path | None = None,
) -> FastAPI:
```

Behaviour (verified in `app.py:33-53`):

- Constructs an `AdminContext` dataclass and attaches it to `app.state.ctx`.
- Creates a `FastAPI` instance with `docs_url=None, redoc_url=None` (Swagger
  UI disabled).
- Mounts `StaticFiles` at `/admin/static` pointing to
  `src/conexus/web/admin/static/`.
- Registers a single route `GET /admin/` that renders `base.html`.
- Registers the `fmt_epoch` Jinja2 global (see §4).

The `connectors_registry_path` parameter defaults to
`Path.cwd() / "connectors" / "registry.json"` when `None` is passed
(`app.py:37-39`).

---

## 3. Dependency injection

`AdminContext` (`src/conexus/web/admin/deps.py:9`) is a plain `@dataclass`:

```python
@dataclass
class AdminContext:
    agents_dir: Path
    data_dir: Path
    connectors_registry_path: Path
```

Routes retrieve it from `request.app.state.ctx`. No FastAPI `Depends()`
wiring exists in Wave 0 — the pattern is in place for Wave 1 routes to adopt.

---

## 4. Jinja2 helpers

One global registered at module load time (`app.py:25`):

| Name | Signature | Output |
|------|-----------|--------|
| `fmt_epoch` | `(epoch: int \| None) -> str` | `"YYYY-MM-DD HH:MM UTC"` or `"—"` |

Implemented at `app.py:18-22`. Templates call it as `{{ ts \| fmt_epoch }}` or
`{{ fmt_epoch(ts) }}`.

---

## 5. Front-end stack

Declared in `src/conexus/web/admin/templates/base.html:7-9`. All assets are
CDN-delivered; no new pip dependencies were added.

| Library | Version | CDN |
|---------|---------|-----|
| Tailwind CSS | latest (CDN play) | `cdn.tailwindcss.com` |
| HTMX | 2.0.3 | `unpkg.com/htmx.org@2.0.3` |
| Alpine.js | 3.x | `unpkg.com/alpinejs@3.x.x` |

`app.css` (`src/conexus/web/admin/static/app.css`) holds project-specific
overrides on top of Tailwind.

The base template exposes a three-item nav (`/admin/`, `/admin/connectors`,
`/admin/connections`) — routes that will be wired in later waves (`base.html:15-18`).

---

## 6. CLI subcommand

`conexus studio` is registered in `_build_parser` (`src/conexus/cli/__main__.py:349-352`):

```
conexus studio [--port PORT] [--no-browser]
```

Default port: `8765`. Handler: `_handle_studio` (`__main__.py:268-287`).

Startup sequence:

1. Reads `CONEXUS_AGENTS_DIR` (default `./agents`) and `CONEXUS_DATA_DIR`
   (default `./data`) from env; creates `data_dir` if absent.
2. Calls `make_admin_app(agents_dir=..., data_dir=...)`.
3. Prints `[conexus] Studio running at http://127.0.0.1:<port>/admin/`.
4. Opens the URL in the system browser unless `--no-browser` is set.
5. Calls `uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")`.

The server binds to loopback only. There is no TLS and no authentication in
Wave 0.

---

## 7. Wave 0 scope and known gaps

Wave 0 delivers the structural skeleton. The following are intentionally
absent:

- No agent-list, connector-list, or connection-list views (nav links 404).
- No HTMX partial endpoints.
- No auth / session (loopback trust is the only protection).
- `routes/__init__.py` and `services/__init__.py` are empty placeholders.

> Verdict: Wave 0 is a confirmed baseline — factory, CLI entry-point, DI
> dataclass, and front-end wiring are all verifiable in source. Business views
> land in Wave 1.

---

## 8. Wave 1 — read-only agent browser + connector marketplace + REPL

Wave 1 ships in Phase 12. All routes are read-only; no writes or installs are
exposed yet.

### 8.1 App factory changes

`make_admin_app` (`src/conexus/web/admin/app.py:30`) now registers three
routers instead of the Wave 0 single catch-all route:

```python
app.include_router(make_agents_router())
app.include_router(make_connectors_router())
app.include_router(make_repl_router())
```

`app.state.templates` is also wired here (line 46) so routes can call
`request.app.state.templates.TemplateResponse(...)` without importing
`_TEMPLATES` directly.

### 8.2 Services

Three pure service modules were added under
`src/conexus/web/admin/services/`:

#### `agent_repo.py`

Public surface:

```python
def list_agents(agents_dir: Path) -> list[AgentSummary]: ...
def read_agent(agents_dir: Path, name: str) -> AgentDetail: ...
```

`AgentSummary` and `AgentDetail` are `frozen=True` dataclasses. `AgentDetail`
carries the full `SkillDocument` (`.frontmatter` + `.body`) obtained via
`parse_skill_file` (`src/conexus/core/config/skill_loader.py`). All field
access goes through `.frontmatter` — the raw YAML dict is never exposed to
routes.

`list_agents` iterates `agents_dir`, skips any subdirectory without a
`SKILL.md`, and silently drops entries that fail to parse (see
`agent_repo.py:39`). `read_agent` raises `FileNotFoundError` on a missing
agent directory.

(see `src/conexus/web/admin/services/agent_repo.py`)

#### `tools_inspector.py`

```python
def scan_tools_file(path: Path) -> list[ToolMethod]: ...
```

AST-parses `tools.py` without importing it. Returns one `ToolMethod` per
public instance method on the first class found in the file. Exclusion rules
(`tools_inspector.py:52-61`):

- Method name starts with `_`.
- Method is decorated with `staticmethod` or `classmethod`.
- First argument is not `self`.

`description` on each `ToolMethod` is extracted from the `_tool_schemas` dict
literal by walking the AST — no `eval`, no import (see `_extract_schemas` at
`tools_inspector.py:32-49`).

(see `src/conexus/web/admin/services/tools_inspector.py`)

#### `runner_proxy.py`

```python
async def run_one_message(
    agent_name: str, message: str, *,
    agents_dir: Path, data_dir: Path, session_id: str
) -> str: ...

def reset_session(agent_name: str, session_id: str) -> None: ...
```

In-process REPL bridge. Sessions are keyed by `(agent_name, session_id)` in a
module-level `_SESSIONS: dict[tuple[str, str], _Session]` (`runner_proxy.py:31`).
First call for a key dynamically imports `tools.py` via `importlib.util`,
calls `create_cli_tools(data_dir)`, builds an `AgentRegistry`, and calls
`build_runtime` (`src/conexus/cli/runner.py`). Subsequent calls on the same
key reuse the session — identity and history persist across turns within one
browser session.

The call chain terminates at `handle_agent_message(s.runtime.handler_cfg,
s.store, s.cap_checker, message)` (`runner_proxy.py:78`), the same entry-point
used by the Telegram adapters.

`_clear_all_sessions()` is a test helper that empties `_SESSIONS`.

(see `src/conexus/web/admin/services/runner_proxy.py`)

### 8.3 Routes

All routers use `APIRouter` with prefix; they are included into the app via
`make_admin_app`.

#### `routes/agents.py` — `make_agents_router()`

| Method | Path | Template | Notes |
|--------|------|----------|-------|
| `GET` | `/admin/` | `agents/list.html` | `list_agents(ctx.agents_dir)` |
| `GET` | `/admin/agents/new` | `agents/new.html` | stub, no form processing |
| `GET` | `/admin/agents/{name}` | `agents/edit.html` | `read_agent` + `scan_tools_file`; `readonly=True` |

Route ordering is intentional: `/admin/agents/new` is registered before
`/admin/agents/{name}` to prevent the path parameter from capturing the literal
string `"new"` (see `routes/agents.py:22`).

The detail route passes `raw_skill_md` (file read from `agent.skill_path`) to
the template for the sidebar.

(see `src/conexus/web/admin/routes/agents.py`)

#### `routes/connectors.py` — `make_connectors_router()`

| Method | Path | Template |
|--------|------|----------|
| `GET` | `/admin/connectors` | `connectors/marketplace.html` |

Reads `ConnectorRegistry.from_file(ctx.connectors_registry_path)` and passes
`list(registry.list())` as `entries` to the template. Connector install is not
wired (button is disabled in the template).

(see `src/conexus/web/admin/routes/connectors.py`)

#### `routes/repl.py` — `make_repl_router()`

| Method | Path | Template | Notes |
|--------|------|----------|-------|
| `POST` | `/admin/agents/{name}/test` | `partials/repl_message.html` | HTMX partial |

Accepts a Form field `message`. Reads the `studio_sid` cookie; if absent,
generates a new `secrets.token_hex(8)` and sets it via `resp.set_cookie`
(`httponly=True, samesite="lax"`). Calls `run_one_message(...)` and returns a
rendered partial. Cookie survives page refresh so multi-turn context persists
across browser navigation within a tab.

(see `src/conexus/web/admin/routes/repl.py`)

### 8.4 Templates

All templates live under `src/conexus/web/admin/templates/`.

| Template | Purpose |
|----------|---------|
| `agents/list.html` | Table: name / role / model / tools count / identity enabled |
| `agents/edit.html` | 3-column grid: back link · 7-tab Alpine form · SKILL.md sidebar |
| `agents/new.html` | Placeholder — Wave 2 |
| `partials/agent_form.html` | 7 Alpine tabs: identity / llm / tools / skills / persistence / budget / prompt (x-data / x-show / x-cloak) |
| `connectors/marketplace.html` | Grid of connector cards |
| `partials/connector_card.html` | Icon, label, category, description, disabled Install button |
| `partials/repl_message.html` | Single REPL turn: role + text with colored left border |

### 8.5 Wave 1 scope and known gaps

- All views are **read-only**. No agent creation, no field editing, no
  connector installation.
- `agents/new.html` is a placeholder — form is wired in Wave 2.
- No auth / session beyond loopback trust (inherited from Wave 0).
- `_SESSIONS` in `runner_proxy.py` is an in-process dict; sessions are lost on
  server restart.

> Verdict: Wave 1 is verified in source — three service modules, three route
> factories, eight templates, and REPL cookie plumbing are all present and
> wired through `make_admin_app`.
