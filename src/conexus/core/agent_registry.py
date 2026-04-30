"""Agent registry — routes tool calls across N backends per agent."""
from __future__ import annotations
import json
from typing import Any
from conexus.core.backends.base import ToolBackend
from conexus.core.backends.python_backend import PythonBackend


class AgentRegistry:
    """Maps agent → list[ToolBackend]; tool-name → backend resolved at call time.

    Tool name uniqueness enforced per agent: collision returns an error instead of
    silently shadowing. Routing uses `backend.list_tools()` — no defaults-allowed.
    """

    def __init__(self) -> None:
        self._backends: dict[str, list[ToolBackend]] = {}

    def register(self, agent_name: str, tools: Any) -> None:
        """Backward-compat: register a Python tools object as a single backend."""
        self.register_backend(agent_name, PythonBackend(tools))

    def register_backend(self, agent_name: str, backend: ToolBackend) -> None:
        self._backends.setdefault(agent_name, []).append(backend)

    def get_tools(self, agent_name: str) -> Any:
        """Backward-compat: return underlying tools object of the first PythonBackend."""
        backends = self._backends.get(agent_name) or []
        for b in backends:
            if isinstance(b, PythonBackend):
                return b._tools
        raise KeyError(f"no PythonBackend for agent {agent_name!r}")

    def agent_names(self) -> list[str]:
        return list(self._backends.keys())

    async def execute_tool(self, agent_name: str, tool_name: str, args: dict) -> str:
        backends = self._backends.get(agent_name)
        if not backends:
            return json.dumps({"error": f"agente desconhecido: {agent_name}"})
        matches = [b for b in backends if tool_name in b.list_tools()]
        if not matches:
            return json.dumps({"error": f"tool desconhecida: {tool_name}"})
        if len(matches) > 1:
            return json.dumps({"error": f"tool collision: {tool_name} in {len(matches)} backends"})
        return await matches[0].execute(tool_name, args)
