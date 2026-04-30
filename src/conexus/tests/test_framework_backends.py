import json
import sys
import pytest
from conexus.core.backends.python_backend import PythonBackend
from conexus.core.backends.mcp_stdio_backend import McpStdioBackend
from conexus.core.agent_registry import AgentRegistry


class _FakeTools:
    async def greet(self, name: str) -> str:
        return f"hello {name}"
    def add(self, a: int, b: int) -> int:
        return a + b


@pytest.mark.asyncio
async def test_python_backend_async():
    b = PythonBackend(_FakeTools())
    result = await b.execute("greet", {"name": "world"})
    assert '"hello world"' in result

@pytest.mark.asyncio
async def test_python_backend_sync():
    b = PythonBackend(_FakeTools())
    result = await b.execute("add", {"a": 1, "b": 2})
    assert "3" in result

@pytest.mark.asyncio
async def test_python_backend_unknown_tool():
    b = PythonBackend(_FakeTools())
    result = await b.execute("missing", {})
    assert "error" in result

@pytest.mark.asyncio
async def test_registry_uses_backend():
    registry = AgentRegistry()
    registry.register("bot", _FakeTools())
    result = await registry.execute_tool("bot", "greet", {"name": "test"})
    assert '"hello test"' in result

@pytest.mark.asyncio
async def test_registry_unknown_agent():
    registry = AgentRegistry()
    result = await registry.execute_tool("nobody", "greet", {})
    assert "error" in result


# Minimal MCP echo server as inline script
_ECHO_SERVER = """
import sys, json
def respond(id, result):
    msg = json.dumps({"jsonrpc":"2.0","id":id,"result":result})
    sys.stdout.write(msg + "\\n")
    sys.stdout.flush()
for line in sys.stdin:
    req = json.loads(line.strip())
    if req["method"] == "initialize":
        respond(req["id"], {"protocolVersion":"2024-11-05","capabilities":{},"serverInfo":{"name":"echo","version":"0.1.0"}})
    elif req["method"] == "tools/list":
        respond(req["id"], {"tools":[{"name":"echo","description":"echo args","inputSchema":{"type":"object","properties":{"msg":{"type":"string"}}}}]})
    elif req["method"] == "tools/call":
        respond(req["id"], {"content":[{"type":"text","text":req["params"]["arguments"]["msg"]}]})
"""

@pytest.mark.asyncio
async def test_mcp_stdio_backend(tmp_path):
    server_script = tmp_path / "echo_server.py"
    server_script.write_text(_ECHO_SERVER)

    backend = McpStdioBackend(command=[sys.executable, str(server_script)])
    await backend.start()
    try:
        result = await backend.execute("echo", {"msg": "hello"})
        data = json.loads(result)
        assert data == "hello"
    finally:
        await backend.stop()
