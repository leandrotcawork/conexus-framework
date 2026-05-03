import json
import time
from dataclasses import dataclass

from .crypto import decrypt, derive_key, encrypt


@dataclass
class TokenRecord:
    access_token: str
    refresh_token: str | None
    expires_at: int
    scopes: list[str]

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at - 30  # 30s clock skew buffer


class TokenVault:
    def __init__(self, store, *, master_secret: bytes) -> None:
        self._store = store
        self._master = master_secret

    def _key(self, user_id: str) -> bytes:
        return derive_key(self._master, salt=user_id.encode())

    def put(
        self,
        user_id: str,
        server_url: str,
        *,
        access_token: str,
        refresh_token: str | None,
        expires_at: int,
        scopes: list[str],
    ) -> None:
        k = self._key(user_id)
        at_enc = encrypt(k, access_token.encode())
        rt_enc = encrypt(k, refresh_token.encode()) if refresh_token else None
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._store.conn as c:
            c.execute(
                """INSERT OR REPLACE INTO oauth_tokens
                (user_id, server_url, access_token_enc, refresh_token_enc,
                 expires_at, scopes_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM oauth_tokens
                  WHERE user_id=? AND server_url=?), ?), ?)""",
                (
                    user_id,
                    server_url,
                    at_enc,
                    rt_enc,
                    expires_at,
                    json.dumps(scopes),
                    user_id,
                    server_url,
                    now,
                    now,
                ),
            )

    def get(self, user_id: str, server_url: str) -> TokenRecord | None:
        with self._store.conn as c:
            cur = c.execute(
                "SELECT access_token_enc, refresh_token_enc, expires_at, scopes_json "
                "FROM oauth_tokens WHERE user_id=? AND server_url=?",
                (user_id, server_url),
            )
            row = cur.fetchone()
        if not row:
            return None
        k = self._key(user_id)
        at = decrypt(k, row[0]).decode()
        rt = decrypt(k, row[1]).decode() if row[1] else None
        return TokenRecord(
            access_token=at,
            refresh_token=rt,
            expires_at=row[2],
            scopes=json.loads(row[3]),
        )

    def delete(self, user_id: str, server_url: str) -> None:
        with self._store.conn as c:
            c.execute(
                "DELETE FROM oauth_tokens WHERE user_id=? AND server_url=?",
                (user_id, server_url),
            )
