import pytest
from conexus.core.oauth.client import OAuthClient
from conexus.core.oauth.metadata import AuthorizationServerMetadata

AS = AuthorizationServerMetadata(
    issuer="https://auth.example/",
    authorization_endpoint="https://auth.example/authorize",
    token_endpoint="https://auth.example/token",
    registration_endpoint="https://auth.example/register",
    code_challenge_methods_supported=["S256"],
)


@pytest.mark.asyncio
async def test_dynamic_client_registration(httpx_mock, tmp_path):
    from conexus.core.memory.sqlite_store import SqliteStore

    store = SqliteStore(":memory:")
    store.init_db()
    client = OAuthClient(
        store=store, master_secret=b"x" * 32, redirect_uri="https://app/oauth/callback"
    )
    httpx_mock.add_response(
        url="https://auth.example/register",
        method="POST",
        json={"client_id": "cli_123", "client_secret": "sec_xyz"},
    )
    cid, csec = await client.ensure_client(AS)
    assert cid == "cli_123"
    assert csec == "sec_xyz"
    # cached on second call (no new HTTP request needed)
    cid2, csec2 = await client.ensure_client(AS)
    assert cid2 == "cli_123"
    assert csec2 == "sec_xyz"


def test_build_authorize_url(tmp_path):
    from conexus.core.memory.sqlite_store import SqliteStore

    store = SqliteStore(":memory:")
    store.init_db()
    client = OAuthClient(
        store=store, master_secret=b"x" * 32, redirect_uri="https://app/oauth/callback"
    )
    url, verifier = client.build_authorize_url(
        AS,
        client_id="cli_123",
        scopes=["calendar.read"],
        resource="https://mcp.example/",
        state="state_token",
    )
    assert url.startswith("https://auth.example/authorize?")
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "resource=https%3A%2F%2Fmcp.example%2F" in url
    assert "scope=calendar.read" in url
    assert "state=state_token" in url
    assert 43 <= len(verifier) <= 128


@pytest.mark.asyncio
async def test_exchange_code(httpx_mock, tmp_path):
    from conexus.core.memory.sqlite_store import SqliteStore

    store = SqliteStore(":memory:")
    store.init_db()
    client = OAuthClient(
        store=store, master_secret=b"x" * 32, redirect_uri="https://app/oauth/callback"
    )
    httpx_mock.add_response(
        url="https://auth.example/token",
        method="POST",
        json={
            "access_token": "at1",
            "refresh_token": "rt1",
            "expires_in": 3600,
            "scope": "calendar.read",
        },
    )
    tokens = await client.exchange_code(
        AS,
        client_id="cli_123",
        code="auth_code",
        code_verifier="verifier",
        resource="https://mcp.example/",
    )
    assert tokens.access_token == "at1"
    assert tokens.refresh_token == "rt1"
    assert tokens.expires_in == 3600


@pytest.mark.asyncio
async def test_refresh(httpx_mock, tmp_path):
    from conexus.core.memory.sqlite_store import SqliteStore

    store = SqliteStore(":memory:")
    store.init_db()
    client = OAuthClient(
        store=store, master_secret=b"x" * 32, redirect_uri="https://app/oauth/callback"
    )
    httpx_mock.add_response(
        url="https://auth.example/token",
        method="POST",
        json={
            "access_token": "at_new",
            "refresh_token": "rt_new",
            "expires_in": 3600,
            "scope": "calendar.read",
        },
    )
    tokens = await client.refresh(
        AS,
        client_id="cli_123",
        client_secret="sec",
        refresh_token="rt_old",
        resource="https://mcp.example/",
    )
    assert tokens.access_token == "at_new"
    assert tokens.refresh_token == "rt_new"
