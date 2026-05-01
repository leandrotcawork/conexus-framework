"""TeamRegistry — lightweight runtime view of a loaded TEAM_PACK."""
from __future__ import annotations
from typing import Any
from conexus.core.team.team_pack import TeamPackDocument


class TeamRegistry:
    def __init__(self, doc: TeamPackDocument) -> None:
        self._doc = doc

    @property
    def members(self) -> list[str]:
        return list(self._doc.frontmatter.members)

    @property
    def manager(self) -> str | None:
        return self._doc.frontmatter.manager

    @property
    def policy(self):
        return self._doc.frontmatter.policy

    @property
    def budget(self):
        return self._doc.frontmatter.budget

    def has_member(self, name: str) -> bool:
        return name in self._doc.frontmatter.members

    def edges_from(self, agent: str) -> list[dict[str, Any]]:
        return [e for e in self._doc.frontmatter.edges if e.get("from") == agent]
