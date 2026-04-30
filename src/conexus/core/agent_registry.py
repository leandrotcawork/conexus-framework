"""Agent registry — routes tool calls to the registered backend per agent."""
from __future__ import annotations
import json
from typing import Any
from conexus.core.backends.base import ToolBackend
from conexus.core.backends.python_backend import PythonBackend


class AgentRegistry:
    """Maps agent names to their ToolBackend."""

    def __init__(self) -> None:
        self._backends: dict[str, ToolBackend] = {}

    def register(self, agent_name: str, tools: Any) -> None:
        """Register a Python tools object. Wraps it in PythonBackend."""
        self._backends[agent_name] = PythonBackend(tools)

    def register_backend(self, agent_name: str, backend: ToolBackend) -> None:
        """Register any backend directly."""
        self._backends[agent_name] = backend

    def get_tools(self, agent_name: str) -> Any:
        """Backward-compat: return underlying tools object for PythonBackend."""
        backend = self._backends.get(agent_name)
        if backend is None:
            raise KeyError(agent_name)
        if isinstance(backend, PythonBackend):
            return backend._tools
        raise TypeError(f"backend for {agent_name!r} is not a PythonBackend")

    def agent_names(self) -> list[str]:
        return list(self._backends.keys())

    async def execute_tool(self, agent_name: str, tool_name: str, args: dict) -> str:
        backend = self._backends.get(agent_name)
        if backend is None:
            return json.dumps({"error": f"agente desconhecido: {agent_name}"})
        return await backend.execute(tool_name, args)
