"""Builtin get_current_time tool - auto-injected into every agent loop."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_BRT = ZoneInfo("America/Sao_Paulo")


class BuiltinTimeTools:
    _tool_schemas = {
        "get_current_time": {
            "description": (
                "Returns current date and time in Sao Paulo (BRT). "
                "Call when the user request is time-sensitive."
            ),
            "params": {},
        },
    }

    def get_current_time(self) -> dict:
        now = datetime.now(_BRT)
        return {
            "brt": now.strftime("%Y-%m-%d %H:%M %Z"),
            "iso": now.isoformat(),
            "weekday": now.strftime("%A"),
        }
