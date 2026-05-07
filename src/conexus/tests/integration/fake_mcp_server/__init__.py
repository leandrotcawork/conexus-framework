"""Fake MCP HTTP server for integration tests. Validates Bearer token."""
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
_valid_tokens: set[str] = set()


def _register_token(token: str) -> None:
    _valid_tokens.add(token)


@app.get("/.well-known/oauth-protected-resource")
async def prm():
    return {
        "resource": "http://localhost:8882/",
        "authorization_servers": ["http://localhost:8881"],
    }


@app.post("/mcp")
async def mcp(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] not in _valid_tokens:
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized"}, "id": None},
            status_code=401,
        )
    body = await request.json()
    method = body.get("method", "")
    rid = body.get("id")
    if method == "initialize":
        return JSONResponse({"jsonrpc": "2.0", "result": {
            "protocolVersion": "2025-06-18",
            "serverInfo": {"name": "fake"},
            "capabilities": {},
        }, "id": rid})
    if method == "notifications/initialized":
        return JSONResponse({})
    if method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "result": {"tools": [
            {"name": "get_time", "description": "Return current time",
             "inputSchema": {"type": "object", "properties": {}}},
        ]}, "id": rid})
    if method == "tools/call":
        return JSONResponse({"jsonrpc": "2.0", "result": {"content": [
            {"type": "text", "text": time.strftime("%Y-%m-%dT%H:%M:%SZ")},
        ]}, "id": rid})
    return JSONResponse(
        {"jsonrpc": "2.0", "error": {"code": -32601, "message": "method not found"}, "id": rid}
    )
