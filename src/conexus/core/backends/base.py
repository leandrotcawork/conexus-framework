"""ToolBackend ABC — all backends implement this interface."""
from __future__ import annotations
from abc import ABC, abstractmethod


class ToolBackend(ABC):
    @abstractmethod
    async def execute(self, tool_name: str, args: dict) -> str:
        """Execute tool; return JSON string (success or {"error": ...})."""

    @property
    def backend_type(self) -> str:
        return "unknown"
