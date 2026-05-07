"""Connections vault status + reauth stub routes."""
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
        store.init_db()
        return request.app.state.templates.TemplateResponse(
            request, "connections/status.html",
            {"title": "Connections", "rows": list_connections(store)},
        )

    @router.post("/{server_url:path}/reauth")
    async def reauth(request: Request, server_url: str) -> RedirectResponse:
        return RedirectResponse("/admin/connectors", status_code=303)

    return router
