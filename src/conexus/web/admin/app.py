"""Conexus Studio admin sub-app."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .deps import AdminContext
from .routes.agents import make_agents_router
from .routes.connections import make_connections_router
from .routes.connectors import make_connectors_router
from .routes.github_wiki import make_github_wiki_router
from .routes.packs import make_packs_router
from .routes.repl import make_repl_router

_HERE = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))


def _fmt_epoch(epoch: int | None) -> str:
    """Render epoch seconds as `YYYY-MM-DD HH:MM UTC`."""
    if epoch is None:
        return "—"
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


_TEMPLATES.env.globals["fmt_epoch"] = _fmt_epoch


def make_admin_app(
    *,
    agents_dir: Path,
    data_dir: Path,
    connectors_registry_path: Path | None = None,
    repo_root: Path | None = None,
) -> FastAPI:
    _repo_root = repo_root or agents_dir.parent
    ctx = AdminContext(
        agents_dir=agents_dir,
        data_dir=data_dir,
        connectors_registry_path=Path(
            connectors_registry_path or _repo_root / "packs" / "registry.json"
        ),
        repo_root=_repo_root,
        allow_unsigned=os.getenv("CONEXUS_ALLOW_UNSIGNED", "").lower() in ("1", "true"),
    )

    app = FastAPI(title="Conexus Studio", docs_url=None, redoc_url=None)
    app.state.ctx = ctx
    app.state.templates = _TEMPLATES
    app.mount("/admin/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    app.include_router(make_agents_router())
    app.include_router(make_connectors_router())
    app.include_router(make_connections_router())
    app.include_router(make_packs_router())
    app.include_router(make_repl_router())
    from conexus.core.memory.sqlite_store import SqliteStore as _SqliteStore
    _store = _SqliteStore(str(data_dir / "conexus.db"))
    _store.init_db()
    app.include_router(make_github_wiki_router(_store))

    return app
