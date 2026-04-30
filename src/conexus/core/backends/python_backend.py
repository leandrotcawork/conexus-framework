"""In-process Python tools backend."""
from __future__ import annotations
import inspect
import json
import traceback
from typing import Any
from .base import ToolBackend


class PythonBackend(ToolBackend):
    def __init__(self, tools_obj: Any) -> None:
        self._tools = tools_obj

    async def execute(self, tool_name: str, args: dict) -> str:
        fn = getattr(self._tools, tool_name, None)
        if fn is None:
            return json.dumps({"error": f"unknown tool: {tool_name}"})
        try:
            result = await fn(**args) if inspect.iscoroutinefunction(fn) else fn(**args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            traceback.print_exc()
            return json.dumps({"error": str(exc)})

    @property
    def backend_type(self) -> str:
        return "python"
