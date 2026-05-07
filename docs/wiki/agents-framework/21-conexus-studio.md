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
    repo_root: Path | None = None,
) -> FastAPI:
```

Behaviour (verified in `app.py:31-58`):

- Constructs an `AdminContext` dataclass and attaches it to `app.state.ctx`.
- Creates a `FastAPI` instance with `docs_url=None, redoc_url=None` (Swagger
  UI disabled).
- Mounts `StaticFiles` at `/admin/static` pointing to
  `src/conexus/web/admin/static/`.
- Registers four routers: `make_agents_router()`, `make_connectors_router()`,
  `make_connections_router()`, `make_repl_router()`.
- Registers the `fmt_epoch` Jinja2 global (see §4).

The `connectors_registry_path` parameter defaults to
`agents_dir.parent / "connectors" / "registry.json"` when `None` is passed
(`app.py:42-44`). `repo_root` defaults to `agents_dir.parent` (`app.py:38`).

---

## 3. Dependency injection

`AdminContext` (`src/conexus/web/admin/deps.py:9`) is a plain `@dataclass`:

```python
@dataclass
class AdminContext:
    agents_dir: Path
    data_dir: Path
    connectors_registry_path: Path
    repo_root: Path
```

`repo_root` was added in Phase A (studio-capability-rollout). It is used by
`detail_view` to locate `connectors/registry.json` and the shared `packs/`
directory relative to the repository root, independent of where `agents_dir`
lives (see `routes/agents.py:64-65`).

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
| `GET` | `/admin/agents/{name}` | `agents/edit.html` | `read_agent` + `build_capability_view`; `readonly=True` |

Route ordering is intentional: `/admin/agents/new` is registered before
`/admin/agents/{name}` to prevent the path parameter from capturing the literal
string `"new"` (see `routes/agents.py:29`).

The detail route calls `build_capability_view(...)` (Phase A) and passes the
resulting `capability` dict to the template. `capability` has four keys:
`native`, `identity`, `packs`, `connectors` (see §9 for details). The flat
`methods` list used in earlier drafts is gone — the template iterates the
individual layers instead.

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
| `partials/agent_form.html` | 7 Alpine tabs: identity / llm / tools / skills / persistence / budget / prompt; Tools tab renders the 4-layer `capability` dict (Phase A) |
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

---

## 9. Phase A — 4-layer capability view (studio-capability-rollout)

Phase A ships the Tools tab as a structured capability browser instead of a
flat method list. All new code lives under
`src/conexus/web/admin/services/`.

### 9.1 New services

#### `capability_view.py`

```python
def build_capability_view(
    *,
    agent_dir: Path,
    skill_refs: list[str],
    identity_enabled: bool,
    connector_registry: Path,
    packs_root: Path,
    model: str,
) -> dict:
```

Aggregates all four layers and returns a single dict with keys `native`,
`identity`, `packs`, `connectors`. Called by `detail_view` in
`routes/agents.py:60-67`. The `model` field is forwarded to `token_counter`
(not yet surfaced in the template but available for future use).

(see `src/conexus/web/admin/services/capability_view.py`)

#### `pack_inspector.py`

```python
def scan_installed_packs(
    agent_dir: Path, *, packs_root: Path, skill_refs: list[str]
) -> list[InstalledPack]:
```

For each `skill_refs` entry resolves the pack under `agent_dir/skills/<name>/`
or `packs_root/<name>/`, parses `SKILL_PACK.md` via `parse_skill_pack`, and
AST-scans `tools.py` via the existing `scan_tools_file`. Returns a list of
`InstalledPack(frozen=True)` dataclasses with fields: `id`, `version`,
`backend`, `source_path`, `body`, `methods`.

(see `src/conexus/web/admin/services/pack_inspector.py`)

#### `connector_inspector.py`

```python
def list_connectors_for_agent(
    skill_refs: list[str], registry_path: Path
) -> list[ConnectorEntry]:
```

Delegates to `PacksRegistry.load(registry_path)` (Phase C), calls
`reg.list(kind="connector")`, filters to entries whose `id` appears in
`skill_refs` (prefix before `@`), and returns `ConnectorEntry(frozen=True)`
dataclasses with fields: `id`, `version`, `label`, `icon`, `category`,
`description`, `server_url`, `scopes`. Returns `[]` if the registry file does
not exist (`PacksRegistry.load` returns an empty registry on missing path).

(see `src/conexus/web/admin/services/connector_inspector.py`)

#### `identity_inspector.py`

```python
def list_identity_tools(*, enabled: bool) -> list[ToolMethod]:
```

Returns `[]` if `identity.enabled` is false. Otherwise calls
`inspect.getsourcefile(IdentityTools)` to locate the source and reuses
`scan_tools_file` — no second import, no eval.

(see `src/conexus/web/admin/services/identity_inspector.py`)

#### `token_counter.py`

```python
def count_schema_tokens(schemas: list[dict], *, model: str) -> int:
```

Delegates to `litellm.token_counter` with the JSON-serialised schema list.
Returns `0` on any error, making the function safe to call without a live
LiteLLM installation.

(see `src/conexus/web/admin/services/token_counter.py`)

### 9.2 Tools tab rendering

`partials/agent_form.html` (Tools tab, lines 56–132) renders four `<section>`
blocks from `capability.*`:

| Section | Data key | Empty state text |
|---------|----------|-----------------|
| Native | `capability.native` | "No native tools." |
| Identity | `capability.identity` | "Identity disabled." |
| Skill Packs | `capability.packs` | "No skill packs installed." |
| Connectors | `capability.connectors` | "No connectors enabled." |

Each entry in `native` and `identity` is a `ToolMethod`; each entry in `packs`
is an `InstalledPack` (exposes `p.id`, `p.version`, `p.backend`, `p.methods`);
each entry in `connectors` is a `ConnectorEntry` (exposes `c.id`, `c.version`,
`c.category`, `c.description`).

### 9.3 `AdminContext` and factory changes

`AdminContext` gains a fourth field `repo_root: Path`
(`src/conexus/web/admin/deps.py:13`). `make_admin_app` accepts an optional
`repo_root` parameter that defaults to `agents_dir.parent` (`app.py:38`).

The `detail_view` route derives registry and packs paths from `ctx.repo_root`:

```python
connector_registry=ctx.repo_root / "packs" / "registry.json",
packs_root=ctx.repo_root / "packs",
```

Both arguments point to the same directory (`packs/`) — Phase C unified the
connector and skill-pack registries into a single file (see §10 below).

(see `src/conexus/web/admin/routes/agents.py:64-65`)

> Verdict: Phase A is verified in source — five new service modules, updated
> `AdminContext`, updated factory signature, and a four-section Tools tab
> template are all wired end-to-end.

---

## 10. Phase C — unified packs registry (studio-capability-rollout)

Phase C replaces the separate `connectors/registry.json` with a single
`packs/registry.json` that covers both skill packs and connectors. The file is
now gone; only `packs/registry.json` exists.

### 10.1 `packs/registry.json` schema

```json
{
  "version": "1.0",
  "entries": [
    {
      "id": "notes",
      "kind": "skill",
      "version": "0.1.0",
      "source": "packs/notes",
      "sha": "<sha1>",
      "ui": {
        "label": "Notes",
        "icon": "puzzle",
        "category": "Skills",
        "description": "..."
      }
    },
    {
      "id": "google_calendar",
      "kind": "connector",
      "version": "1.0",
      "source": "https://...",
      "sha": "unsigned",
      "server_url": "https://mcp.google.com/calendar",
      "scopes": ["https://www.googleapis.com/auth/calendar"],
      "ui": { "label": "Google Calendar", "icon": "calendar", "category": "Productivity", "description": "..." }
    }
  ]
}
```

`kind` is `"skill"` or `"connector"`. `server_url` and `scopes` are
connector-only fields; they default to `""` and `[]` on skill entries.

(see `packs/registry.json`)

### 10.2 `PacksRegistry` API

New Python package at `src/conexus/core/packs/registry.py`.

```python
class PacksRegistry:
    @classmethod
    def load(cls, path: Path) -> "PacksRegistry": ...
    def get(self, pack_id: str) -> PackEntry: ...          # raises RegistryError if missing
    def list(self, *, kind: Kind | None = None) -> list[PackEntry]: ...

@dataclass(frozen=True)
class PackEntry:
    id: str
    kind: Literal["skill", "connector"]
    version: str
    source: str
    sha: str
    ui: PackUI
    server_url: str   # connector-only, default ""
    scopes: list[str] # connector-only, default []

@dataclass(frozen=True)
class PackUI:
    label: str
    icon: str
    category: str
    description: str

class RegistryError(ValueError): ...
```

`PacksRegistry.load(path)` returns an empty registry (no error) when `path`
does not exist (`registry.py:43-44`). `list(kind="connector")` filters to
connector entries; `list(kind="skill")` filters to skill entries; `list()`
returns all entries.

(see `src/conexus/core/packs/registry.py`)

### 10.3 Impact on `connector_inspector.py`

`list_connectors_for_agent` now calls `PacksRegistry.load(registry_path)` and
filters with `reg.list(kind="connector")`. The `registry_path` passed by
`detail_view` is `ctx.repo_root / "packs" / "registry.json"` — the unified
file (see §9.3 and `routes/agents.py:64`).

### 10.4 `connectors_registry_path` in `AdminContext`

`AdminContext.connectors_registry_path` is still present in `deps.py` and
`make_admin_app` still accepts the `connectors_registry_path` parameter
(defaulting to `agents_dir.parent / "connectors" / "registry.json"`). This
field is used by `make_connectors_router()` (the marketplace route), which
still calls `ConnectorRegistry.from_file(ctx.connectors_registry_path)`. That
path is now a dangling reference unless the caller overrides it — the
marketplace route is effectively broken until it is migrated to `PacksRegistry`.
This is a known gap as of Phase C.

> Verdict: Phase C is verified in source — `packs/registry.json` exists,
> `src/conexus/core/packs/registry.py` is the new loader, `connector_inspector.py`
> delegates to `PacksRegistry`, and `detail_view` already points at the unified
> path. The connectors marketplace route (`make_connectors_router`) retains a
> stale reference to `ConnectorRegistry` and has not been migrated yet.

---

## 11. Phase D — pack install / uninstall (studio-capability-rollout)

Phase D wires live install and uninstall of skill packs from both the agent
detail view and a dedicated marketplace page. Two new modules were added:
`src/conexus/core/packs/installer.py` and
`src/conexus/web/admin/routes/packs.py`.

### 11.1 `installer.py` — pack service

Public surface (`src/conexus/core/packs/installer.py`):

```python
class InstallError(RuntimeError): ...

def install_pack(
    pack_id: str,
    *,
    agent_dir: Path,
    packs_root: Path,
    registry_path: Path,
    allow_unsigned: bool = False,
) -> None: ...

def uninstall_pack(pack_id: str, *, agent_dir: Path) -> None: ...
```

Key implementation details (all verified in `installer.py`):

- **Path traversal guard** — `_safe_name(value, label)` rejects any `pack_id`
  or `agent_name` containing `/`, `\`, or starting with `.`, or being empty
  (`installer.py:47-49`).
- **SHA pin** — `install_pack` calls `reg.get(pack_id)` then checks
  `entry.sha == "unsigned"`; if true and `allow_unsigned=False`, raises
  `InstallError` with an explicit message (`installer.py:67-70`).
- **Atomic SKILL.md edit** — writes to `SKILL.md.tmp` then calls
  `tmp.replace(path)` (atomic on POSIX; best-effort on Windows)
  (`installer.py:27-28`).
- **Rollback on failure** — both `install_pack` and `uninstall_pack` snapshot
  the original `SKILL.md` text before editing; any exception during
  `_append_skill_ref` / `_remove_skill_ref` restores the backup and re-raises
  as `InstallError` (`installer.py:80-85`, `91-97`).
- `uninstall_pack` does not consult the registry — it only reads and rewrites
  `agent_dir/SKILL.md`, so it works even if the registry entry has been
  removed.

### 11.2 `routes/packs.py` — HTTP endpoints

`make_packs_router()` registers three endpoints under the `/admin` prefix
(`src/conexus/web/admin/routes/packs.py`):

| Method | Path | Action |
|--------|------|--------|
| `GET` | `/admin/packs` | Marketplace view — lists all skill packs and connectors from `packs/registry.json` |
| `POST` | `/admin/agents/{name}/packs/{pack_id}/install` | Calls `install_pack(...)`, redirects `303 → /admin/agents/{name}` |
| `POST` | `/admin/agents/{name}/packs/{pack_id}/uninstall` | Calls `uninstall_pack(...)`, redirects `303 → /admin/agents/{name}` |

Both mutating routes run `_safe_name` on `name` and `pack_id` before touching
the filesystem, returning HTTP 400 on a validation failure (`packs.py:31-35`,
`55-59`). An unknown agent directory returns HTTP 404.

`install_pack` receives `allow_unsigned=getattr(ctx, "allow_unsigned", False)`,
delegating the unsigned-pack policy to `AdminContext` (`packs.py:45`).

Security note documented in `packs.py:3-5`: no CSRF tokens are used. The
assumption is localhost-only access; if the admin is exposed beyond loopback,
CSRF middleware must be added before these POST handlers.

### 11.3 `skills.html` — marketplace template

`src/conexus/web/admin/templates/skills.html` renders two sections
(Skill Packs and Connectors) as a card grid. Each card shows `s.id`,
`s.version`, and `s.ui.description`. It does not expose install buttons —
installation is driven from the agent detail page.

### 11.4 Agent form — install / remove UI

`src/conexus/web/admin/templates/partials/agent_form.html` (Skill Packs
section, lines 93–141) was updated in two ways:

1. **Remove button** — each installed pack card includes a
   `<button type="button" hx-post="/admin/agents/{name}/packs/{id}/uninstall"
   hx-swap="none" hx-on::after-request="window.location.reload()">` element
   (`agent_form.html:100-104`). No nested `<form>` is used; HTMX issues the
   POST directly from the button so the outer agent-save form is never
   inadvertently submitted (see commit d5abb6c — nested forms are invalid
   HTML5 and browsers strip them, which previously caused Remove to submit the
   outer save form and wipe `tools:` from `SKILL.md`).
2. **"Add a pack" disclosure** — a `<details>` element lists uninstalled packs
   from the `available_packs` template variable, filtered to exclude already-
   installed IDs (`agent_form.html:121-140`). Each row has an Install button
   using the same HTMX-button pattern:
   `<button type="button" hx-post="/admin/agents/{name}/packs/{id}/install"
   hx-swap="none" hx-on::after-request="window.location.reload()">`.

Both buttons set `hx-swap="none"` — HTMX discards the server response body —
and reload the page via the `hx-on::after-request` hook, which re-renders the
full capability view with updated pack state.

`available_packs` is injected by `detail_view` in `routes/agents.py:81-83`:

```python
"available_packs": PacksRegistry.load(
    ctx.repo_root / "packs" / "registry.json"
).list(kind="skill"),
```

### 11.5 `AdminContext` and factory changes

`AdminContext` gains a fifth field (`src/conexus/web/admin/deps.py:14`):

```python
allow_unsigned: bool = False
```

`make_admin_app` reads the env var `CONEXUS_ALLOW_UNSIGNED` and sets
`allow_unsigned=True` when its value is `"1"` or `"true"` (case-insensitive)
(`app.py:48`). `make_packs_router` is now registered by the factory
(`app.py:59`).

### 11.6 Phase D scope and known gaps

- The marketplace (`/admin/packs`) is read-only; install is only available from
  the agent detail page.
- No CSRF protection — loopback trust is the only protection (inherited from
  Wave 0).
- `tmp.replace(path)` is described as "not crash-safe on Windows" in the source
  comment (`installer.py:28`); it is atomic on POSIX.

> Verdict: Phase D is verified in source — `installer.py` (atomic edit,
> rollback, SHA pin, path traversal guard), `routes/packs.py` (three endpoints,
> `_safe_name` validation, `allow_unsigned` delegation), `skills.html`
> (marketplace template), updated `agent_form.html` (Remove + Install buttons
> as HTMX `hx-post` buttons with no nested `<form>`, per commit d5abb6c), and
> `AdminContext.allow_unsigned` / `CONEXUS_ALLOW_UNSIGNED` env wiring are all
> present and wired through `make_admin_app`.
