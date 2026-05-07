import pytest
from conexus.core.oauth.metadata import discover_protected_resource, discover_authorization_server


@pytest.mark.asyncio
async def test_protected_resource_metadata(httpx_mock):
    httpx_mock.add_response(
        url="https://mcp.example/.well-known/oauth-protected-resource",
        json={"resource": "https://mcp.example/",
              "authorization_servers": ["https://auth.example/"]})
    meta = await discover_protected_resource("https://mcp.example/")
    assert meta.authorization_servers == ["https://auth.example/"]


@pytest.mark.asyncio
async def test_authorization_server_metadata(httpx_mock):
    httpx_mock.add_response(
        url="https://auth.example/.well-known/oauth-authorization-server",
        json={"issuer": "https://auth.example/",
              "authorization_endpoint": "https://auth.example/authorize",
              "token_endpoint": "https://auth.example/token",
              "registration_endpoint": "https://auth.example/register",
              "code_challenge_methods_supported": ["S256"]})
    meta = await discover_authorization_server("https://auth.example/")
    assert meta.token_endpoint == "https://auth.example/token"
    assert "S256" in meta.code_challenge_methods_supported
