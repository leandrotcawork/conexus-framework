"""GitHub App OAuth install callback for wiki backend."""
from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from conexus.core.memory.sqlite_store import SqliteStore


def make_github_wiki_router(store: SqliteStore) -> APIRouter:
    router = APIRouter(prefix="/admin/oauth/github")

    @router.get("/start")
    async def start(
        agent: str = Query(...),
        repo: str = Query(...),
    ) -> RedirectResponse:
        app_slug = os.environ["GITHUB_APP_SLUG"]
        nonce = secrets.token_urlsafe(16)
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO oauth_pkce_state (nonce, code_verifier, created_at)"
                " VALUES (?, ?, datetime('now'))",
                (nonce, f"gh:{agent}:{repo}"),  # prefix isolates from Phase 11 PKCE rows
            )
            conn.commit()
        gh_url = f"https://github.com/apps/{app_slug}/installations/new?state={nonce}"
        return RedirectResponse(gh_url)

    @router.get("/callback")
    async def callback(
        installation_id: int = Query(...),
        state: str = Query(...),
    ) -> RedirectResponse:
        with store.connect() as conn:
            row = conn.execute(
                "SELECT code_verifier FROM oauth_pkce_state WHERE nonce=?", (state,)
            ).fetchone()
            if not row:
                raise HTTPException(400, "invalid state")
            payload = row["code_verifier"]
            if not payload.startswith("gh:"):
                raise HTTPException(400, "invalid state")
            _, agent, repo_slug = payload.split(":", 2)
            conn.execute("DELETE FROM oauth_pkce_state WHERE nonce=?", (state,))
            conn.commit()
        store.github_app_install_set(agent, repo_slug, installation_id)
        return RedirectResponse(f"/admin/agents/{agent}")

    return router
