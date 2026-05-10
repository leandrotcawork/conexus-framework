"""GitHub App JWT signing and installation-token minting."""
from __future__ import annotations

import time
from datetime import datetime

import httpx
import jwt

# module-level cache: installation_id -> (token, expires_epoch)
_TOKEN_CACHE: dict[int, tuple[str, float]] = {}


def _make_jwt(app_id: str, private_key_pem: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": app_id},
        private_key_pem,
        algorithm="RS256",
    )


def get_installation_token(app_id: str, private_key_pem: str, installation_id: int) -> str:
    """Return a valid GitHub App installation token (cached until 5 min before expiry)."""
    token, expires = _TOKEN_CACHE.get(installation_id, ("", 0.0))
    if token and time.time() < expires - 300:
        return token
    app_jwt = _make_jwt(app_id, private_key_pem)
    resp = httpx.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
    _TOKEN_CACHE[installation_id] = (data["token"], expires_at)
    return data["token"]
