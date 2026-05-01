"""TrifectaGuard — per-turn deterministic taint tracker."""
from __future__ import annotations
from .tags import DataClass, auto_tag


class TrifectaViolation(Exception):
    """Raised when a tool call violates the Trifecta rule."""


class TrifectaGuard:
    """Stateful per-turn guard. Create one instance per handle_agent_message call."""

    def __init__(
        self,
        tool_tags: dict[str, str],
        *,
        trust_boundary_cleared: bool = False,
        seed_taint: set[DataClass] | None = None,
    ) -> None:
        self._tool_tags: dict[str, DataClass] = {}
        for name, tag in tool_tags.items():
            try:
                self._tool_tags[name] = DataClass(tag)
            except ValueError:
                pass  # invalid tag string — caught at check time
        self._trust_cleared = trust_boundary_cleared
        self._taint: set[DataClass] = set(seed_taint) if seed_taint else set()

    @classmethod
    def from_handoff(cls, tool_tags: dict[str, str], handoff) -> "TrifectaGuard":
        from conexus.core.team.handoff import Handoff
        assert isinstance(handoff, Handoff)
        return cls(
            tool_tags,
            trust_boundary_cleared=handoff.trust_boundary_cleared,
            seed_taint=handoff.tags,
        )

    def check_and_record(self, tool_name: str) -> DataClass:
        """Resolve tag, check rule, record taint. Returns tag. Raises on violation."""
        if tool_name in self._tool_tags:
            tag = self._tool_tags[tool_name]
        else:
            tag = auto_tag(tool_name)
            if tag is None:
                raise ValueError(
                    f"Tool '{tool_name}' has no data_class tag and heuristic could not "
                    "auto-tag it. Add an explicit entry in data_classes: in SKILL_PACK.md."
                )

        if (
            tag == DataClass.external_write
            and not self._trust_cleared
            and DataClass.untrusted_read in self._taint
            and DataClass.private_read in self._taint
        ):
            raise TrifectaViolation(
                f"TrifectaGuard blocked '{tool_name}' (external_write): "
                "turn taint contains untrusted_read + private_read — possible exfil path."
            )

        self._taint.add(tag)
        return tag
