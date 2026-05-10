"""Agent routes — list, new, detail, save, delete."""
from __future__ import annotations

import shutil

import yaml
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from conexus.core.llm.catalog import configured_providers, llm_options
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.packs.installer import InstallError, _safe_name
from conexus.core.packs.registry import PacksRegistry
from ..services.agent_repo import list_agents, read_agent
from ..services.skill_writer import write_skill_md
from ..services.template_lib import TEMPLATES, scaffold_agent
from ..services.validators import validate_agent


def make_agents_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    # ── list ──────────────────────────────────────────────────────────────────
    @router.get("/", response_class=HTMLResponse)
    async def list_view(request: Request) -> HTMLResponse:
        ctx = request.app.state.ctx
        agents = list_agents(ctx.agents_dir)
        return request.app.state.templates.TemplateResponse(
            request, "agents/list.html", {"title": "Agents", "agents": agents}
        )

    # CRITICAL: /agents/new registered before /agents/{name}
    @router.get("/agents/new", response_class=HTMLResponse)
    async def new_view(request: Request) -> HTMLResponse:
        return request.app.state.templates.TemplateResponse(
            request, "agents/new.html",
            {"title": "New agent", "templates": list(TEMPLATES)},
        )

    @router.post("/agents/new")
    async def new_create(
        request: Request,
        name: str = Form(...),
        template: str = Form(...),
    ) -> Response:
        ctx = request.app.state.ctx
        try:
            scaffold_agent(ctx.agents_dir, name, template=template)
        except (ValueError, FileExistsError) as exc:
            return Response(str(exc), status_code=400)
        return RedirectResponse(f"/admin/agents/{name}", status_code=303)

    # ── detail (read-only) ────────────────────────────────────────────────────
    @router.get("/agents/{name}", response_class=HTMLResponse)
    async def detail_view(request: Request, name: str) -> HTMLResponse:
        ctx = request.app.state.ctx
        try:
            agent = read_agent(ctx.agents_dir, name)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        _store = SqliteStore(str(ctx.data_dir / "conexus.db"))
        _store.init_db()
        github_install = _store.github_app_install_get(name)
        from conexus.web.admin.services.capability_view import build_capability_view
        fm = agent.skill.frontmatter
        capability = build_capability_view(
            agent_dir=ctx.agents_dir / name,
            skill_refs=fm.skills or [],
            identity_enabled=bool(fm.identity and fm.identity.enabled),
            connector_registry=ctx.repo_root / "packs" / "registry.json",
            packs_root=ctx.repo_root / "packs",
            model=fm.llm.model if fm.llm else "gpt-4o-mini",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "agents/edit.html",
            {
                "title": agent.name,
                "agent": agent,
                "fm": fm,
                "body": agent.skill.body,
                "capability": capability,
                "github_install": github_install,
                "readonly": True,
                "raw_skill_md": agent.skill_path.read_text(encoding="utf-8"),
                "llm_options": llm_options(configured_only=False),
                "configured_providers": list(configured_providers()),
                "available_packs": PacksRegistry.load(
                    ctx.repo_root / "packs" / "registry.json"
                ).list(kind="skill"),
            },
        )

    # ── save ──────────────────────────────────────────────────────────────────
    @router.post("/agents/{name}/github-wiki/disconnect")
    async def github_wiki_disconnect(request: Request, name: str) -> RedirectResponse:
        ctx = request.app.state.ctx
        store = SqliteStore(str(ctx.data_dir / "conexus.db"))
        store.init_db()
        store.github_app_install_delete(name)
        return RedirectResponse(f"/admin/agents/{name}", status_code=303)

    @router.post("/agents/{name}", response_class=HTMLResponse)
    async def save(
        request: Request,
        name: str,
        role: str = Form(...),
        goal: str = Form(...),
        llm_provider: str = Form(...),
        llm_model: str = Form(...),
        llm_temperature: str = Form("0.4"),
        tools: str = Form(""),
        body: str = Form(""),
    ) -> HTMLResponse:
        ctx = request.app.state.ctx
        try:
            _safe_name(name, "agent name")
        except InstallError as e:
            raise HTTPException(400, str(e)) from e
        skill_path = ctx.agents_dir / name / "SKILL.md"
        if not skill_path.exists():
            raise HTTPException(404, name)
        raw = skill_path.read_text(encoding="utf-8")
        existing = yaml.safe_load(raw.split("---", 2)[1]) or {}
        existing.update({
            "role": role,
            "goal": goal,
            "llm": {
                **existing.get("llm", {}),
                "provider": llm_provider,
                "model": llm_model,
                "temperature": float(llm_temperature),
            },
            "tools": [t.strip() for t in tools.split(",") if t.strip()],
        })
        write_skill_md(skill_path, existing, body)
        res = validate_agent(ctx.agents_dir, name)
        return request.app.state.templates.TemplateResponse(
            request, "partials/validation_errors.html",
            {"errors": res.errors, "warnings": res.warnings, "saved": res.ok, "agent_name": name},
            status_code=422 if not res.ok else 200,
        )

    # ── preview (no write) ────────────────────────────────────────────────────
    @router.post("/agents/{name}/preview", response_class=HTMLResponse)
    async def preview(
        request: Request, name: str,
        role: str = Form(""), goal: str = Form(""),
        llm_provider: str = Form("openai"), llm_model: str = Form("gpt-4o-mini"),
        llm_temperature: str = Form("0.4"), tools: str = Form(""), body: str = Form(""),
    ) -> HTMLResponse:
        fm = {
            "name": name, "role": role, "goal": goal,
            "llm": {"provider": llm_provider, "model": llm_model, "temperature": float(llm_temperature)},
            "tools": [t.strip() for t in tools.split(",") if t.strip()],
        }
        yml = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
        rendered = f"---\n{yml}---\n{body}"
        return request.app.state.templates.TemplateResponse(
            request, "partials/agent_yaml_preview.html", {"yaml": rendered}
        )

    # ── delete ────────────────────────────────────────────────────────────────
    @router.delete("/agents/{name}")
    async def delete(request: Request, name: str) -> Response:
        ctx = request.app.state.ctx
        try:
            _safe_name(name, "agent name")
        except InstallError as e:
            raise HTTPException(400, str(e)) from e
        d = ctx.agents_dir / name
        if not d.exists() or not d.is_dir():
            raise HTTPException(404, name)
        shutil.rmtree(d)
        return Response(status_code=204)

    return router
