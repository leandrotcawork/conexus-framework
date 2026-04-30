"""ToolBackend ABC — all backends implement this interface."""
from __future__ import annotations
from abc import ABC, abstractmethod


class ToolBackend(ABC):
    @abstractmethod
    async def execute(self, tool_name: str, args: dict) -> str:
        """Execute tool; return JSON string (success or {"error": ...})."""

    @abstractmethod
    def list_tools(self) -> list[str]:
        """Return tool names this backend handles. Used by registry for routing."""

    @property
    def backend_type(self) -> str:
        return "unknown"
