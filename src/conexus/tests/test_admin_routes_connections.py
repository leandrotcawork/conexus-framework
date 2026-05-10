import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.web.admin.app import make_admin_app


def _seed(tmp_path: Path, *, expires_at_s: int, server="https://mcp.notion.so") -> None:
    store = SqliteStore(str(tmp_path / "conexus.db"))
    store.init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    with store.conn as c:
        c.execute(
            "INSERT INTO oauth_tokens(user_id, server_url, access_token_enc, "
            "refresh_token_enc, expires_at, scopes_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("local", server, b"x", None, expires_at_s,
             json.dumps(["read"]), now_iso, now_iso),
        )


def test_connections_page_renders(tmp_path: Path) -> None:
    _seed(tmp_path, expires_at_s=int(time.time()) + 30 * 86400)
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/connections")
    assert resp.status_code == 200
    assert "mcp.notion.so" in resp.text
    assert ">ok<" in resp.text or "ok\n" in resp.text or " ok" in resp.text


def test_connections_empty_state(tmp_path: Path) -> None:
    store = SqliteStore(":memory:")
    store.init_db()
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.get("/admin/connections")
    assert resp.status_code == 200
    assert "No connections yet" in resp.text


def test_reauth_redirects_to_marketplace(tmp_path: Path) -> None:
    _seed(tmp_path, expires_at_s=int(time.time()) - 86400)
    client = TestClient(make_admin_app(agents_dir=tmp_path, data_dir=tmp_path))
    resp = client.post(
        "/admin/connections/https://mcp.notion.so/reauth",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/admin/connectors")
