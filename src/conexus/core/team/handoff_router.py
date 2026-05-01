"""HandoffRouter — resolves Handoff.to_agent.

Resolution order:
  1. If to_agent != "auto" and member exists, use it.
  2. Match `auto: true` edges from sender — first match wins.
  3. Match `when: ...` edges — first match where Python eval against payload is True.
  4. Fall back to manager.
  5. No manager → raise.
"""
from __future__ import annotations
from typing import Any
from conexus.core.team.handoff import Handoff
from conexus.core.team.team_registry import TeamRegistry


class HandoffRouter:
    def __init__(self, registry: TeamRegistry) -> None:
        self._reg = registry

    def route(self, handoff: Handoff) -> str:
        if handoff.to_agent != "auto":
            if not self._reg.has_member(handoff.to_agent):
                raise ValueError(f"unknown target: {handoff.to_agent}")
            return handoff.to_agent
        for edge in self._reg.edges_from(handoff.from_agent):
            if edge.get("auto") is True:
                return edge["to"]
            cond = edge.get("when")
            if cond and self._eval(cond, handoff.payload):
                return edge["to"]
        if self._reg.manager:
            return self._reg.manager
        raise ValueError("no edge match and no manager")

    @staticmethod
    def _eval(expr: str, payload: dict[str, Any]) -> bool:
        """Sandboxed eval — payload is the only namespace; all builtins blocked.

        Edges in TEAM_PACK.md are author-controlled (committed in repo); risk
        surface = author shooting own foot. No untrusted input reaches this.
        """
        class _Box:
            def __init__(self, d: dict[str, Any]) -> None:
                for k, v in d.items():
                    setattr(self, k, _Box(v) if isinstance(v, dict) else v)

        try:
            return bool(eval(expr, {"__builtins__": {}}, {"task": _Box(payload.get("task", {}))}))
        except Exception:
            return False
