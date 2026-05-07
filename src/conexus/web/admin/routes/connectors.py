"""Connector marketplace + install + diff routes."""
from __future__ import annotations

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from conexus.core.connectors.registry import ConnectorRegistry

from ..services.connector_installer import install_connector
from ..services.tool_diff import diff_for_connector


def make_connectors_router() -> APIRouter:
    router = APIRouter(prefix="/admin/connectors")

    @router.get("", response_class=HTMLResponse)
    async def marketplace(request: Request, agent: str = Query("")) -> HTMLResponse:
        ctx = request.app.state.ctx
        registry = ConnectorRegistry.from_file(ctx.connectors_registry_path)
        return request.app.state.templates.TemplateResponse(
            request, "connectors/marketplace.html",
            {"title": "Connectors", "entries": list(registry.list()), "current_agent": agent},
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

    @router.get("/{connector}/diff", response_class=HTMLResponse)
    async def diff(request: Request, connector: str, agent: str = Query("")) -> HTMLResponse:
        ctx = request.app.state.ctx
        registry = ConnectorRegistry.from_file(ctx.connectors_registry_path)
        entry = registry.get(connector)
        if entry is None:
            return Response(f"connector {connector!r} not found", status_code=404)
        tool_names = entry.scopes  # scopes proxy for tool names at MVP
        summary = diff_for_connector(
            connector_name=connector,
            new_tool_names=tool_names,
            sample_descriptions={n: entry.ui_description for n in tool_names},
        )
        return request.app.state.templates.TemplateResponse(
            request, "partials/diff_modal.html",
            {"d": summary, "connector": connector, "agent": agent},
        )

    return router
