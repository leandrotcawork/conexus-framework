"""Connector marketplace route (read-only in Wave 1)."""
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
            {"title": "Connectors", "entries": list(registry.list())},
        )

    return router
