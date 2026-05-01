"""TeamLoader — validates a TEAM_PACK against available agents + budget shares."""
from __future__ import annotations
from pathlib import Path
from conexus.core.team.team_pack import parse_team_pack, TeamPackDocument


class TeamLoader:
    def __init__(self, available_agents: set[str]) -> None:
        self._available = available_agents

    def load(self, pack_path: str | Path) -> TeamPackDocument:
        doc = parse_team_pack(pack_path)
        unknown = [m for m in doc.frontmatter.members if m not in self._available]
        if unknown:
            raise ValueError(f"unknown member: {unknown[0]}")
        if doc.frontmatter.manager and doc.frontmatter.manager not in doc.frontmatter.members:
            raise ValueError(f"manager {doc.frontmatter.manager!r} not in members")
        share_total = sum(doc.frontmatter.budget.shares.values())
        if abs(share_total - 1.0) > 0.01:
            raise ValueError(f"budget shares must sum to 1.0 (got {share_total})")
        unknown_shares = set(doc.frontmatter.budget.shares) - set(doc.frontmatter.members)
        if unknown_shares:
            raise ValueError(f"share for unknown member(s): {sorted(unknown_shares)}")
        return doc
