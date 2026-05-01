"""MCP stdio backend — launches a subprocess MCP server and dispatches via JSON-RPC 2.0."""
from __future__ import annotations
import asyncio
import json
from typing import Any
from .base import ToolBackend


class McpStdioBackend(ToolBackend):
    """Subprocess-based MCP server backend. Call start() before execute(), stop() at teardown."""

    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        self._command = command
        self._env = env
        self._proc: asyncio.subprocess.Process | None = None
        self._id = 0
        self._initialized = False
        self._tool_names: list[str] = []
        self._call_lock = asyncio.Lock()

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
        )
        await self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "conexus", "version": "0.1.0"},
        })
        tools_result = await self._call("tools/list", {})
        self._tool_names = [t["name"] for t in (tools_result.get("tools") or [])]
        self._initialized = True

    async def stop(self) -> None:
        if self._proc:
            self._proc.terminate()
            await self._proc.wait()
            self._proc = None
            self._initialized = False

    async def _call(self, method: str, params: dict) -> Any:
        assert self._proc and self._proc.stdin and self._proc.stdout
        async with self._call_lock:
            self._id += 1
            req_id = self._id
            req = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
            self._proc.stdin.write((req + "\n").encode())
            await self._proc.stdin.drain()
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    raise RuntimeError("MCP server closed stdout")
                try:
                    frame = json.loads(line.decode())
                except json.JSONDecodeError:
                    continue
                if "id" not in frame:
                    continue  # notification — skip
                if frame["id"] != req_id:
                    continue  # stale frame — lock should prevent, drop defensively
                if "error" in frame:
                    raise RuntimeError(f"MCP error: {frame['error']}")
                return frame.get("result")

    async def execute(self, tool_name: str, args: dict) -> str:
        if not self._initialized:
            raise RuntimeError("McpStdioBackend.start() must be called before execute()")
        try:
            result = await self._call("tools/call", {"name": tool_name, "arguments": args})
            content = result.get("content", [])
            text_parts = [c["text"] for c in content if c.get("type") == "text"]
            return json.dumps("\n".join(text_parts) if len(text_parts) != 1 else text_parts[0])
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def list_tools(self) -> list[str]:
        return list(self._tool_names)

    @property
    def backend_type(self) -> str:
        return "mcp-stdio"
