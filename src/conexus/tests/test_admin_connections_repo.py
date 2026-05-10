import json
import time
from datetime import datetime, timezone
from pathlib import Path

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.web.admin.services.connections_repo import list_connections, status_for


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_list_returns_token_rows(tmp_path: Path) -> None:
    store = SqliteStore(":memory:")
    store.init_db()
    now = int(time.time())
    with store.conn as c:
        c.execute(
            "INSERT INTO oauth_tokens(user_id, server_url, access_token_enc, "
            "refresh_token_enc, expires_at, scopes_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("local", "https://mcp.notion.so", b"x", None,
             now + 30 * 86400, json.dumps(["read", "write"]), _now_iso(), _now_iso()),
        )
    rows = list_connections(store)
    assert len(rows) == 1
    assert rows[0].server_url == "https://mcp.notion.so"
    assert rows[0].scopes == ["read", "write"]
    assert rows[0].status == "ok"


def test_status_classification() -> None:
    now = int(time.time())
    assert status_for(now + 30 * 86400) == "ok"
    assert status_for(now + 3 * 86400) == "expiring"
    assert status_for(now - 86400) == "expired"
    assert status_for(None) == "ok"


def test_scopes_json_malformed_falls_back_to_empty(tmp_path: Path) -> None:
    store = SqliteStore(":memory:")
    store.init_db()
    now = int(time.time())
    with store.conn as c:
        c.execute(
            "INSERT INTO oauth_tokens(user_id, server_url, access_token_enc, "
            "refresh_token_enc, expires_at, scopes_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("local", "https://x.test", b"x", None, now + 86400,
             "not-json", _now_iso(), _now_iso()),
        )
    rows = list_connections(store)
    assert rows[0].scopes == []
