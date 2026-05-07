"""Read oauth_tokens rows for the Studio connections page."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Literal

Status = Literal["ok", "expiring", "expired"]

_EXPIRING_WINDOW_S = 7 * 86400  # 7 days


@dataclass(frozen=True)
class Connection:
    server_url: str
    user_id: str
    expires_at: int | None  # epoch seconds; None if NULL row
    scopes: list[str]
    status: Status


def status_for(expires_at: int | None) -> Status:
    if expires_at is None:
        return "ok"
    now = int(time.time())
    if expires_at < now:
        return "expired"
    if expires_at - now < _EXPIRING_WINDOW_S:
        return "expiring"
    return "ok"


def _decode_scopes(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        v = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(s) for s in v] if isinstance(v, list) else []


def list_connections(store) -> list[Connection]:
    with store.conn as c:
        rows = c.execute(
            "SELECT server_url, user_id, expires_at, scopes_json FROM oauth_tokens "
            "ORDER BY server_url"
        ).fetchall()
    return [
        Connection(
            server_url=r[0],
            user_id=r[1],
            expires_at=int(r[2]) if r[2] is not None else None,
            scopes=_decode_scopes(r[3]),
            status=status_for(int(r[2]) if r[2] is not None else None),
        )
        for r in rows
    ]
