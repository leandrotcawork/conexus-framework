"""Streamable HTTP MCP backend (MCP 2025-06-18 transport)."""
from __future__ import annotations
import asyncio
import json
import time
from typing import Any
import httpx
from .base import ToolBackend
from ..oauth.errors import NeedsAuthError, TokenExpiredError


def _parse_sse_result(body: str, req_id: int) -> Any:
    """Extract JSON-RPC result from SSE stream. Returns result field or raises."""
    for line in body.splitlines():
        if line.startswith("data:"):
            frame = json.loads(line[5:].strip())
            if frame.get("id") == req_id:
                if "error" in frame:
                    err = frame["error"]
                    raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
                return frame["result"]
    raise RuntimeError("MCP SSE stream ended without matching response frame")


class McpHttpBackend(ToolBackend):
    def __init__(self, *, server_url: str, vault, user_id: str, scopes: list[str],
                 oauth_client=None, asm=None) -> None:
        # Normalize: _server_url = canonical base (vault key); _rpc_url = base + /mcp
        base = server_url.rstrip("/")
        if base.endswith("/mcp"):
            self._server_url = base[:-4]
        else:
            self._server_url = base
        self._rpc_url = self._server_url + "/mcp"
        self._vault = vault
        self._user_id = user_id
        self._scopes = scopes
        self._oauth = oauth_client
        self._asm = asm
        self._tool_names: list[str] = []
        self._initialized = False
        self._session_id: str | None = None
        self._id = 0
        self._lock = asyncio.Lock()
        self._client: httpx.AsyncClient | None = None

    def _bearer(self) -> str:
        rec = self._vault.get(self._user_id, self._server_url)
        if rec is None:
            raise NeedsAuthError(self._server_url, self._scopes)
        if rec.is_expired:
            if rec.refresh_token and self._oauth and self._asm:
                raise TokenExpiredError()
            raise NeedsAuthError(self._server_url, self._scopes)
        return rec.access_token

    async def _refresh_then_get(self) -> str:
        rec = self._vault.get(self._user_id, self._server_url)
        if rec is None or not rec.refresh_token or not self._oauth or not self._asm:
            raise NeedsAuthError(self._server_url, self._scopes)
        cid, csec = await self._oauth.ensure_client(self._asm)
        try:
            new = await self._oauth.refresh(self._asm, client_id=cid, client_secret=csec,
                                            refresh_token=rec.refresh_token,
                                            resource=self._server_url)
        except Exception:
            self._vault.delete(self._user_id, self._server_url)
            raise NeedsAuthError(self._server_url, self._scopes)
        self._vault.put(self._user_id, self._server_url,
                        access_token=new.access_token,
                        refresh_token=new.refresh_token,
                        expires_at=int(time.time()) + new.expires_in,
                        scopes=self._scopes)
        return new.access_token

    def _headers(self, token: str) -> dict:
        h = {
            "Authorization": f"Bearer {token}",
            "MCP-Protocol-Version": "2025-06-18",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    async def _post(self, token: str, payload: dict) -> httpx.Response:
        c = self._client or httpx.AsyncClient()
        return await c.post(self._rpc_url, json=payload, timeout=30.0,
                            headers=self._headers(token))

    def _parse_response(self, r: httpx.Response, req_id: int) -> Any:
        ct = r.headers.get("content-type", "")
        if "text/event-stream" in ct:
            return _parse_sse_result(r.text, req_id)
        frame = r.json()
        if "error" in frame:
            err = frame["error"]
            raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
        return frame["result"]

    async def _call(self, method: str, params: dict, *, capture_session: bool = False) -> Any:
        async with self._lock:
            try:
                token = self._bearer()
            except TokenExpiredError:
                token = await self._refresh_then_get()
            self._id += 1
            req_id = self._id
            req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            r = await self._post(token, req)
            if r.status_code == 401:
                try:
                    token = await self._refresh_then_get()
                except NeedsAuthError:
                    raise
                r = await self._post(token, req)
                if r.status_code == 401:
                    raise NeedsAuthError(self._server_url, self._scopes)
            r.raise_for_status()
            if capture_session:
                sid = r.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
            return self._parse_response(r, req_id)

    async def _notify(self, method: str, params: dict | None = None) -> None:
        """Send JSON-RPC notification (no id, no response expected)."""
        try:
            token = self._bearer()
        except (NeedsAuthError, TokenExpiredError):
            return
        notif: dict = {"jsonrpc": "2.0", "method": method}
        if params:
            notif["params"] = params
        c = self._client or httpx.AsyncClient()
        await c.post(self._rpc_url, json=notif, timeout=10.0,
                     headers=self._headers(token))

    async def start(self) -> None:
        self._client = httpx.AsyncClient()
        await self._call("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "conexus", "version": "0.1.0"},
        }, capture_session=True)
        self._initialized = True
        # Required by MCP spec — must precede further requests
        await self._notify("notifications/initialized")
        tools: list[dict] = []
        cursor = None
        while True:
            params: dict = {"cursor": cursor} if cursor else {}
            result = await self._call("tools/list", params)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        self._tool_names = [t["name"] for t in tools]

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def execute(self, tool_name: str, args: dict) -> str:
        if not self._initialized:
            raise RuntimeError("McpHttpBackend.start() must be called before execute()")
        try:
            result = await self._call("tools/call", {"name": tool_name, "arguments": args})
            content = result.get("content", [])
            text_parts = [c["text"] for c in content if c.get("type") == "text"]
            return json.dumps("\n".join(text_parts) if len(text_parts) != 1 else text_parts[0])
        except NeedsAuthError:
            raise
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def list_tools(self) -> list[str]:
        return list(self._tool_names)

    @property
    def backend_type(self) -> str:
        return "mcp-http"
