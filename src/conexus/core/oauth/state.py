import time
from dataclasses import dataclass

import jwt


class StateInvalid(Exception):
    pass


class StateExpired(Exception):
    pass


@dataclass
class StatePayload:
    user_id: str
    server_url: str
    return_to: str
    nonce: str  # random nonce — used to look up verifier server-side


def _now() -> float:
    return time.time()


def encode_state(
    secret: bytes,
    *,
    user_id: str,
    server_url: str,
    return_to: str,
    nonce: str,
    ttl_seconds: int = 300,
) -> str:
    """Sign state JWT. code_verifier is NOT included — stored server-side keyed by nonce."""
    if len(secret) < 32:
        raise ValueError("state secret must be >= 32 bytes")
    now = int(_now())
    payload = {
        "uid": user_id,
        "su": server_url,
        "ret": return_to,
        "nonce": nonce,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_state(secret: bytes, token: str) -> StatePayload:
    try:
        # Decode without expiry validation so we can check via _now() (monkeypatch-friendly).
        d = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False})
    except jwt.PyJWTError:
        raise StateInvalid()
    if _now() > d["exp"]:
        raise StateExpired()
    return StatePayload(
        user_id=d["uid"],
        server_url=d["su"],
        return_to=d["ret"],
        nonce=d["nonce"],
    )
