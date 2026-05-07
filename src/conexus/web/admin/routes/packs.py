"""Routes: /admin/packs (marketplace list) and /admin/agents/{name}/packs/{id}/(install|uninstall)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from conexus.core.packs.installer import InstallError, install_pack, uninstall_pack
from conexus.core.packs.registry import PacksRegistry


def make_packs_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.get("/packs", response_class=HTMLResponse)
    async def list_packs(request: Request) -> HTMLResponse:
        ctx = request.app.state.ctx
        reg = PacksRegistry.load(ctx.repo_root / "packs" / "registry.json")
        return request.app.state.templates.TemplateResponse(
            request, "skills.html",
            {"title": "Skills", "skills": reg.list(kind="skill"),
             "connectors": reg.list(kind="connector")},
        )

    @router.post("/agents/{name}/packs/{pack_id}/install")
    async def install(request: Request, name: str, pack_id: str) -> Response:
        ctx = request.app.state.ctx
        agent_dir = ctx.agents_dir / name
        if not agent_dir.exists():
            raise HTTPException(404, name)
        try:
            install_pack(
                pack_id,
                agent_dir=agent_dir,
                packs_root=ctx.repo_root / "packs",
                registry_path=ctx.repo_root / "packs" / "registry.json",
                allow_unsigned=getattr(ctx, "allow_unsigned", False),
            )
        except InstallError as e:
            raise HTTPException(400, str(e)) from e
        return RedirectResponse(f"/admin/agents/{name}", status_code=303)

    @router.post("/agents/{name}/packs/{pack_id}/uninstall")
    async def uninstall(request: Request, name: str, pack_id: str) -> Response:
        ctx = request.app.state.ctx
        agent_dir = ctx.agents_dir / name
        if not agent_dir.exists():
            raise HTTPException(404, name)
        try:
            uninstall_pack(pack_id, agent_dir=agent_dir)
        except InstallError as e:
            raise HTTPException(400, str(e)) from e
        return RedirectResponse(f"/admin/agents/{name}", status_code=303)

    return router
