import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from conexus.core.oauth.client import OAuthClient
from conexus.core.oauth.metadata import discover_authorization_server, discover_protected_resource
from conexus.core.oauth.state import StateExpired, StateInvalid, decode_state
from conexus.core.vault.token_vault import TokenVault


def make_router(
    *, store, master_secret: bytes, state_secret: bytes, redirect_uri: str, on_connected=None
) -> APIRouter:
    router = APIRouter(prefix="/oauth")
    vault = TokenVault(store, master_secret=master_secret)
    oauth = OAuthClient(store=store, master_secret=master_secret, redirect_uri=redirect_uri)

    @router.get("/start")
    async def start(state: str):
        try:
            payload = decode_state(state_secret, state)
        except (StateInvalid, StateExpired):
            raise HTTPException(400, "invalid or expired state")
        prm = await discover_protected_resource(payload.server_url)
        asm = await discover_authorization_server(prm.authorization_servers[0])
        client_id, _ = await oauth.ensure_client(asm)
        scopes: list[str] = []
        url, verifier = oauth.build_authorize_url(
            asm, client_id=client_id, scopes=scopes,
            resource=payload.server_url, state=state)
        with store.conn as c:
            c.execute(
                "INSERT OR REPLACE INTO oauth_pkce_state (nonce, code_verifier, created_at) "
                "VALUES (?, ?, ?)",
                (payload.nonce, verifier, time.strftime("%Y-%m-%dT%H:%M:%S")))
        return RedirectResponse(url, status_code=302)

    @router.get("/callback")
    async def callback(code: str, state: str):
        try:
            payload = decode_state(state_secret, state)
        except (StateInvalid, StateExpired):
            raise HTTPException(400, "invalid or expired state")
        with store.conn as c:
            row = c.execute(
                "SELECT code_verifier FROM oauth_pkce_state WHERE nonce=?",
                (payload.nonce,)).fetchone()
            if row:
                c.execute("DELETE FROM oauth_pkce_state WHERE nonce=?", (payload.nonce,))
        if not row:
            raise HTTPException(400, "PKCE verifier not found or expired")
        code_verifier = row[0]
        prm = await discover_protected_resource(payload.server_url)
        asm = await discover_authorization_server(prm.authorization_servers[0])
        cid, csec = await oauth.ensure_client(asm)
        tokens = await oauth.exchange_code(
            asm, client_id=cid, client_secret=csec,
            code=code, code_verifier=code_verifier, resource=payload.server_url)
        vault.put(
            payload.user_id, payload.server_url,
            access_token=tokens.access_token, refresh_token=tokens.refresh_token,
            expires_at=int(time.time()) + tokens.expires_in,
            scopes=tokens.scope.split() if tokens.scope else [])
        if on_connected:
            await on_connected(user_id=payload.user_id, server_url=payload.server_url,
                               return_to=payload.return_to)
        if payload.return_to:
            return RedirectResponse(payload.return_to, status_code=302)
        return HTMLResponse("<h1>Conectado ✅</h1><p>Pode voltar pro Telegram.</p>")

    return router
