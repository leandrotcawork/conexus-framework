"""Connector marketplace + install routes."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from conexus.core.connectors.registry import ConnectorRegistry

from ..services.connector_installer import install_connector


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

    @router.post("/{connector}/install")
    async def install(
        request: Request, connector: str, agent: str = Form(...)
    ) -> Response:
        ctx = request.app.state.ctx
        try:
            install_connector(
                agents_dir=ctx.agents_dir,
                agent_name=agent,
                connector_name=connector,
                registry_path=ctx.connectors_registry_path,
            )
        except (ValueError, FileNotFoundError) as exc:
            return Response(str(exc), status_code=400)
        return RedirectResponse(f"/admin/agents/{agent}", status_code=303)

    return router
