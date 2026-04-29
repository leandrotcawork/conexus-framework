"""Tests for the unified agent tool-dispatch registry."""
import json

import pytest

from conexus.core.agent_registry import AgentRegistry


class _FakeTools:
    def sync_add(self, a: int, b: int) -> int:
        return a + b

    async def async_mul(self, a: int, b: int) -> int:
        return a * b

    def boom(self) -> None:
        raise RuntimeError("kaboom")


@pytest.mark.asyncio
async def test_sync_tool_dispatch():
    reg = AgentRegistry()
    reg.register("a", _FakeTools())
    out = await reg.execute_tool("a", "sync_add", {"a": 2, "b": 3})
    assert json.loads(out) == 5


@pytest.mark.asyncio
async def test_async_tool_dispatch():
    reg = AgentRegistry()
    reg.register("a", _FakeTools())
    out = await reg.execute_tool("a", "async_mul", {"a": 4, "b": 5})
    assert json.loads(out) == 20


@pytest.mark.asyncio
async def test_unknown_agent():
    reg = AgentRegistry()
    out = await reg.execute_tool("nobody", "whatever", {})
    assert "error" in json.loads(out)


@pytest.mark.asyncio
async def test_unknown_tool():
    reg = AgentRegistry()
    reg.register("a", _FakeTools())
    out = await reg.execute_tool("a", "nope", {})
    assert "error" in json.loads(out)


@pytest.mark.asyncio
async def test_tool_exception_captured_as_json_error():
    reg = AgentRegistry()
    reg.register("a", _FakeTools())
    out = await reg.execute_tool("a", "boom", {})
    parsed = json.loads(out)
    assert "kaboom" in parsed["error"]


def test_agent_names_and_get_tools():
    reg = AgentRegistry()
    t = _FakeTools()
    reg.register("a", t)
    assert reg.agent_names() == ["a"]
    assert reg.get_tools("a") is t
