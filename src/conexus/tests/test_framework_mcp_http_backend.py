import pytest
from conexus.core.backends.mcp_http_backend import McpHttpBackend
from conexus.core.oauth.errors import NeedsAuthError


class _FakeVault:
    def __init__(self, rec):
        self._rec = rec

    def get(self, user_id, server_url):
        return self._rec

    def put(self, *a, **kw):
        pass

    def delete(self, *a, **kw):
        pass


class _Rec:
    def __init__(self, at, exp=False, rt=None):
        self.access_token = at
        self.is_expired = exp
        self.refresh_token = rt


@pytest.mark.asyncio
async def test_no_token_raises_needs_auth():
    backend = McpHttpBackend(server_url="https://mcp.example/",
                             vault=_FakeVault(None), user_id="u1",
                             scopes=["x"], oauth_client=None)
    with pytest.raises(NeedsAuthError) as e:
        await backend.start()
    # vault key should be canonical base (no /mcp)
    assert e.value.server_url == "https://mcp.example"


@pytest.mark.asyncio
async def test_lists_tools_with_bearer(httpx_mock):
    # initialize response (JSON, with session-id header)
    httpx_mock.add_response(
        url="https://mcp.example/mcp", method="POST",
        json={"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}, "protocolVersion": "2025-06-18"}},
        headers={"content-type": "application/json", "Mcp-Session-Id": "session-abc"})
    # notifications/initialized response (no body, status 202 typical)
    httpx_mock.add_response(url="https://mcp.example/mcp", method="POST", status_code=202)
    # tools/list response
    httpx_mock.add_response(
        url="https://mcp.example/mcp", method="POST",
        json={"jsonrpc": "2.0", "id": 2,
              "result": {"tools": [{"name": "list_events", "inputSchema": {"type": "object", "properties": {}}},
                                   {"name": "create_event", "inputSchema": {"type": "object", "properties": {}}}]}},
        headers={"content-type": "application/json"})

    backend = McpHttpBackend(server_url="https://mcp.example/mcp",
                             vault=_FakeVault(_Rec("at1")), user_id="u1",
                             scopes=["x"], oauth_client=None)
    await backend.start()
    assert "list_events" in backend.list_tools()
    assert "create_event" in backend.list_tools()
    assert backend._session_id == "session-abc"


@pytest.mark.asyncio
async def test_sse_response_parsed(httpx_mock):
    # initialize as JSON
    httpx_mock.add_response(
        url="https://mcp.example/mcp", method="POST",
        json={"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}},
        headers={"content-type": "application/json"})
    # notifications/initialized
    httpx_mock.add_response(url="https://mcp.example/mcp", method="POST", status_code=202)
    # tools/list as SSE stream
    sse_body = 'data: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"sse_tool"}]}}\n\n'
    httpx_mock.add_response(
        url="https://mcp.example/mcp", method="POST",
        text=sse_body,
        headers={"content-type": "text/event-stream"})

    backend = McpHttpBackend(server_url="https://mcp.example/",
                             vault=_FakeVault(_Rec("at1")), user_id="u1",
                             scopes=["x"], oauth_client=None)
    await backend.start()
    assert "sse_tool" in backend.list_tools()


@pytest.mark.asyncio
async def test_url_normalization():
    """Vault key is base server_url, never /mcp suffix."""
    fake = _FakeVault(None)
    b1 = McpHttpBackend(server_url="https://mcp.example/", vault=fake, user_id="u1",
                        scopes=["x"], oauth_client=None)
    b2 = McpHttpBackend(server_url="https://mcp.example/mcp", vault=fake, user_id="u1",
                        scopes=["x"], oauth_client=None)
    assert b1._server_url == b2._server_url == "https://mcp.example"
    assert b1._rpc_url == b2._rpc_url == "https://mcp.example/mcp"
