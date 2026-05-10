"""REPL route — POST /admin/agents/{name}/test."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from fastapi.responses import Response

from ..services.runner_proxy import reset_session, run_one_message


def make_repl_router() -> APIRouter:
    router = APIRouter(prefix="/admin/agents")

    @router.post("/{name}/test", response_class=HTMLResponse)
    async def test(request: Request, name: str, message: str = Form(...)) -> HTMLResponse:
        ctx = request.app.state.ctx
        sid = request.cookies.get("studio_sid") or secrets.token_hex(8)
        try:
            reply = await run_one_message(
                name, message, agents_dir=ctx.agents_dir, data_dir=ctx.data_dir, session_id=sid
            )
            role, text = "agent", reply
        except Exception as exc:  # noqa: BLE001 — surface upstream LLM/tool errors to UI
            role, text = "error", f"{type(exc).__name__}: {exc}"
        resp = request.app.state.templates.TemplateResponse(
            request, "partials/repl_message.html", {"role": role, "text": text}
        )
        resp.set_cookie("studio_sid", sid, httponly=True, samesite="lax")
        return resp

    @router.post("/{name}/test/reset")
    async def reset(request: Request, name: str) -> Response:
        sid = request.cookies.get("studio_sid")
        if sid:
            reset_session(name, sid)
        return Response(status_code=204)

    return router
