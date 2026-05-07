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
) -> FastAPI:
    ctx = AdminContext(
        agents_dir=agents_dir,
        data_dir=data_dir,
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
        return request.app.state.templates.TemplateResponse(
            request, "base.html", {"title": "Conexus Studio", "body_partial": None}
        )

    return app
