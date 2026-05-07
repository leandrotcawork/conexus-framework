"""Agent list + detail routes (read-only in Wave 1)."""
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

    # CRITICAL: /agents/new must be registered before /agents/{name}
    @router.get("/agents/new", response_class=HTMLResponse)
    async def new_view(request: Request) -> HTMLResponse:
        return request.app.state.templates.TemplateResponse(
            request, "agents/new.html", {"title": "New Agent"}
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
                "title": agent.name,
                "agent": agent,
                "fm": agent.skill.frontmatter,
                "body": agent.skill.body,
                "methods": methods,
                "readonly": True,
                "raw_skill_md": agent.skill_path.read_text(encoding="utf-8"),
            },
        )

    return router
