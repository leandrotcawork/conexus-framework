import pytest
from conexus.core.backends.python_backend import PythonBackend
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
