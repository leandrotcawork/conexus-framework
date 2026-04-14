"""Agent registry — central store of live agent instances.

Agents register their tools instance here. The registry provides unified
tool dispatch so agent handlers don't need separate execute_tool closures.

Usage::

    registry = AgentRegistry()
    registry.register("ana", ana_tools)
    registry.register("pesquisador", pesq_tools)

    # In a handler:
    result = await registry.execute_tool("ana", "calendar_list_events", {...})
"""

from __future__ import annotations

import inspect
import json
import traceback
from typing import Any


class AgentRegistry:
    """Holds the live tools instance for every registered agent."""

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def register(self, agent_name: str, tools: Any) -> None:
        """Register a tools instance under *agent_name*."""
        self._tools[agent_name] = tools

    def get_tools(self, agent_name: str) -> Any:
        """Return the tools instance; raises KeyError if not registered."""
        return self._tools[agent_name]

    def agent_names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute_tool(self, agent_name: str, tool_name: str, args: dict) -> str:
        """Dispatch *tool_name* on the tools instance for *agent_name*.

        Returns a JSON string (success or ``{"error": ...}``).
        Handles both sync and async tool methods.
        """
        tools = self._tools.get(agent_name)
        if tools is None:
            return json.dumps({"error": f"agente desconhecido: {agent_name}"})

        fn = getattr(tools, tool_name, None)
        if fn is None:
            return json.dumps({"error": f"ferramenta desconhecida: {tool_name}"})

        try:
            result = await fn(**args) if inspect.iscoroutinefunction(fn) else fn(**args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            traceback.print_exc()
            return json.dumps({"error": str(exc)})
