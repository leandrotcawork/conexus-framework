"""E2E: NeedsAuth → /callback flow → token in vault → MCP tools call."""
import threading
import time

import pytest
import uvicorn

from conexus.core.backends.mcp_http_backend import McpHttpBackend
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.oauth.client import OAuthClient
from conexus.core.oauth.errors import NeedsAuthError
from conexus.core.oauth.metadata import discover_authorization_server, discover_protected_resource
from conexus.core.vault.token_vault import TokenVault


def _run_server(app, port: int) -> None:
    uvicorn.run(app, port=port, log_level="error")


@pytest.fixture(scope="module")
def servers():
    from conexus.tests.integration.fake_mcp_server import _register_token
    from conexus.tests.integration.fake_mcp_server import app as mcp_app
    from conexus.tests.integration.fake_oauth_server import app as as_app

    threading.Thread(target=_run_server, args=(as_app, 8881), daemon=True).start()
    threading.Thread(target=_run_server, args=(mcp_app, 8882), daemon=True).start()
    time.sleep(0.8)
    yield _register_token


@pytest.mark.asyncio
async def test_full_flow_no_auth_then_callback_then_call(tmp_path, servers):
    register_token = servers
    store = SqliteStore(str(tmp_path / "e.db"))
    store.init_db()
    vault = TokenVault(store, master_secret=b"m" * 32)
    oauth = OAuthClient(store=store, master_secret=b"m" * 32,
                        redirect_uri="http://localhost:8883/cb")

    backend = McpHttpBackend(
        server_url="http://localhost:8882/",
        vault=vault, user_id="u1", scopes=["x"],
        oauth_client=oauth, asm=None)

    # No token yet — start() must raise NeedsAuthError
    with pytest.raises(NeedsAuthError):
        await backend.start()

    # Simulate /callback: discover AS, DCR, exchange code
    prm = await discover_protected_resource("http://localhost:8882/")
    asm = await discover_authorization_server(prm.authorization_servers[0])
    cid, csec = await oauth.ensure_client(asm)
    tokens = await oauth.exchange_code(
        asm, client_id=cid, client_secret=csec,
        code="code_ignored_by_fake",
        code_verifier="x" * 43,
        resource="http://localhost:8882/")

    # Register issued token with fake MCP server
    register_token(tokens.access_token)

    # Store in vault keyed by base URL matching backend's _server_url (no trailing slash, no /mcp)
    vault.put("u1", "http://localhost:8882",
              access_token=tokens.access_token,
              refresh_token=tokens.refresh_token,
              expires_at=int(time.time()) + tokens.expires_in,
              scopes=["x"])

    # Now start() succeeds and tools are listed
    await backend.start()
    assert "get_time" in backend.list_tools()

    result = await backend.execute("get_time", {})
    assert "T" in result  # ISO timestamp like 2026-05-07T...

    await backend.stop()
