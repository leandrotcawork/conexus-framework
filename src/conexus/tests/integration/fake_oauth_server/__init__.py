"""Fake OAuth AS for integration tests. No persistence — test only."""
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

app = FastAPI()

_clients: dict[str, str] = {}   # client_id → client_secret
_codes: dict[str, dict] = {}    # code → metadata (not validated on exchange)
_tokens: dict[str, str] = {}    # access_token → client_id


@app.get("/.well-known/oauth-authorization-server")
async def as_metadata():
    base = "http://localhost:8881"
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "registration_endpoint": f"{base}/register",
        "code_challenge_methods_supported": ["S256"],
    }


@app.post("/register")
async def register(request: Request):
    cid = f"cli_{secrets.token_hex(4)}"
    csec = f"sec_{secrets.token_hex(8)}"
    _clients[cid] = csec
    return {"client_id": cid, "client_secret": csec}


@app.get("/authorize")
async def authorize(response_type: str, client_id: str, redirect_uri: str,
                    code_challenge: str, code_challenge_method: str, state: str,
                    resource: str = ""):
    code = f"code_{secrets.token_hex(8)}"
    _codes[code] = {"client_id": client_id, "code_challenge": code_challenge, "resource": resource}
    return RedirectResponse(f"{redirect_uri}?code={code}&state={state}", status_code=302)


@app.post("/token")
async def token(request: Request):
    # Always issue a token — code validation skipped for E2E test purposes.
    at = f"at_{secrets.token_hex(16)}"
    rt = f"rt_{secrets.token_hex(16)}"
    _tokens[at] = at
    return {"access_token": at, "refresh_token": rt, "expires_in": 3600, "token_type": "Bearer"}
