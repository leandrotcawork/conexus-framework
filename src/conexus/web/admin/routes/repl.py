"""REPL route — POST /admin/agents/{name}/test."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ..services.runner_proxy import run_one_message


def make_repl_router() -> APIRouter:
    router = APIRouter(prefix="/admin/agents")

    @router.post("/{name}/test", response_class=HTMLResponse)
    async def test(request: Request, name: str, message: str = Form(...)) -> HTMLResponse:
        ctx = request.app.state.ctx
        sid = request.cookies.get("studio_sid") or secrets.token_hex(8)
        reply = await run_one_message(
            name, message, agents_dir=ctx.agents_dir, data_dir=ctx.data_dir, session_id=sid
        )
        resp = request.app.state.templates.TemplateResponse(
            request, "partials/repl_message.html", {"role": "agent", "text": reply}
        )
        resp.set_cookie("studio_sid", sid, httponly=True, samesite="lax")
        return resp

    return router
