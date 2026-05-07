import secrets as _secrets

from fastapi.testclient import TestClient

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.oauth.state import encode_state
from conexus.web.app import make_app


def test_start_redirects_to_authorize(tmp_path, httpx_mock):
    store = SqliteStore(str(tmp_path / "w.db"))
    store.init_db()
    state_secret = b"s" * 32
    app = make_app(
        store=store, master_secret=b"m" * 32, state_secret=state_secret,
        redirect_uri="https://app/oauth/callback")

    httpx_mock.add_response(
        url="https://mcp.example/.well-known/oauth-protected-resource",
        json={"resource": "https://mcp.example/",
              "authorization_servers": ["https://auth.example/"]})
    httpx_mock.add_response(
        url="https://auth.example/.well-known/oauth-authorization-server",
        json={"issuer": "https://auth.example/",
              "authorization_endpoint": "https://auth.example/authorize",
              "token_endpoint": "https://auth.example/token",
              "registration_endpoint": "https://auth.example/register",
              "code_challenge_methods_supported": ["S256"]})
    httpx_mock.add_response(
        url="https://auth.example/register", method="POST",
        json={"client_id": "cli_1"})

    state = encode_state(
        state_secret, user_id="u1",
        server_url="https://mcp.example/", return_to="tg://chat/1",
        nonce=_secrets.token_urlsafe(16))
    client = TestClient(app)
    r = client.get(f"/oauth/start?state={state}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://auth.example/authorize?")
