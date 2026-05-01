"""McpStdioBackend must correlate JSON-RPC responses by id when notifications interleave."""
from __future__ import annotations
import asyncio
import json
import pytest
from conexus.core.backends.mcp_stdio_backend import McpStdioBackend


class _FakeProc:
    """Stdin/stdout pair that emits a notification before the real response."""

    def __init__(self):
        self.stdin = self
        self.stdout = self
        self._inbox: asyncio.Queue = asyncio.Queue()
        self._closed = False

    def write(self, data):
        try:
            req = json.loads(data.decode().strip())
        except Exception:
            return
        self._inbox.put_nowait(
            (json.dumps({"jsonrpc": "2.0", "method": "log/message",
                         "params": {"level": "info", "msg": "hi"}}) + "\n").encode()
        )
        if req["method"] == "initialize":
            self._inbox.put_nowait(
                (json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {}}) + "\n").encode()
            )
        elif req["method"] == "tools/list":
            self._inbox.put_nowait(
                (json.dumps({"jsonrpc": "2.0", "id": req["id"],
                             "result": {"tools": [{"name": "ping"}]}}) + "\n").encode()
            )

    async def drain(self):
        return None

    async def readline(self):
        return await self._inbox.get()

    def terminate(self):
        self._closed = True

    async def wait(self):
        return 0


@pytest.mark.asyncio
async def test_correlation_skips_notifications(monkeypatch):
    backend = McpStdioBackend(["dummy"])

    async def fake_create(*args, **kwargs):
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    await backend.start()
    assert backend.list_tools() == ["ping"]
    await backend.stop()


@pytest.mark.asyncio
async def test_concurrent_calls_serialize_via_lock(monkeypatch):
    """Concurrent _call invocations serialize via lock — no stale-id interleave."""
    backend = McpStdioBackend(["dummy"])

    async def fake_create(*a, **kw):
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    await backend.start()

    results = await asyncio.gather(*(backend._call("tools/list", {}) for _ in range(5)))
    assert all(r == {"tools": [{"name": "ping"}]} for r in results)
    await backend.stop()
