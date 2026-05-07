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
> will land in subsequent waves.
