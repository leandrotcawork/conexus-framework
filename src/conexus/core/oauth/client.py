import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from ..vault.crypto import decrypt, derive_key, encrypt
from .metadata import AuthorizationServerMetadata
from .pkce import generate_pkce_pair


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str | None
    token_type: str = "Bearer"


class OAuthClient:
    def __init__(self, *, store, master_secret: bytes, redirect_uri: str) -> None:
        self._store = store
        self._csec_key = derive_key(master_secret, salt=b"oauth_clients")
        self._redirect_uri = redirect_uri

    async def ensure_client(self, asm: AuthorizationServerMetadata) -> tuple[str, str | None]:
        """DCR per RFC 7591. Cached in oauth_clients table."""
        with self._store.conn as conn:
            row = conn.execute(
                "SELECT client_id, client_secret_enc FROM oauth_clients WHERE authorization_server=?",
                (asm.issuer,),
            ).fetchone()
        if row:
            cid, csec_enc = row[0], row[1]
            csec = decrypt(self._csec_key, csec_enc).decode() if csec_enc else None
            return cid, csec
        if not asm.registration_endpoint:
            raise RuntimeError(
                f"AS {asm.issuer} has no registration_endpoint and no static client configured"
            )
        async with httpx.AsyncClient() as c:
            r = await c.post(
                asm.registration_endpoint,
                json={
                    "client_name": "Conexus",
                    "redirect_uris": [self._redirect_uri],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "client_secret_basic",
                },
                timeout=10.0,
            )
            r.raise_for_status()
            d = r.json()
        cid, csec = d["client_id"], d.get("client_secret")
        csec_enc = encrypt(self._csec_key, csec.encode()) if csec else None
        with self._store.conn as conn:
            conn.execute(
                """INSERT INTO oauth_clients
                (authorization_server, client_id, client_secret_enc, registered_at)
                VALUES (?, ?, ?, ?)""",
                (asm.issuer, cid, csec_enc, time.strftime("%Y-%m-%dT%H:%M:%S")),
            )
        return cid, csec

    def build_authorize_url(
        self,
        asm: AuthorizationServerMetadata,
        *,
        client_id: str,
        scopes: list[str],
        resource: str,
        state: str,
    ) -> tuple[str, str]:
        verifier, challenge, _ = generate_pkce_pair()
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": self._redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": resource,
        }
        return f"{asm.authorization_endpoint}?{urlencode(params)}", verifier

    async def exchange_code(
        self,
        asm: AuthorizationServerMetadata,
        *,
        client_id: str,
        client_secret: str | None = None,
        code: str,
        code_verifier: str,
        resource: str,
    ) -> TokenResponse:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "resource": resource,
        }
        auth = (client_id, client_secret) if client_secret else None
        async with httpx.AsyncClient() as c:
            r = await c.post(asm.token_endpoint, data=data, auth=auth, timeout=10.0)
            r.raise_for_status()
            d = r.json()
        return TokenResponse(
            access_token=d["access_token"],
            refresh_token=d.get("refresh_token"),
            expires_in=d.get("expires_in", 3600),
            scope=d.get("scope"),
        )

    async def refresh(
        self,
        asm: AuthorizationServerMetadata,
        *,
        client_id: str,
        client_secret: str | None,
        refresh_token: str,
        resource: str,
    ) -> TokenResponse:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "resource": resource,
        }
        auth = (client_id, client_secret) if client_secret else None
        async with httpx.AsyncClient() as c:
            r = await c.post(asm.token_endpoint, data=data, auth=auth, timeout=10.0)
            r.raise_for_status()
            d = r.json()
        return TokenResponse(
            access_token=d["access_token"],
            refresh_token=d.get("refresh_token", refresh_token),
            expires_in=d.get("expires_in", 3600),
            scope=d.get("scope"),
        )
