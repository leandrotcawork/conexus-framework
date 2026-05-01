"""TEAM_PACK.md — YAML frontmatter parser. Mirrors pack_loader.py shape."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Literal
import yaml
from pydantic import BaseModel, Field


class TeamBudget(BaseModel):
    team_daily_usd: float
    shares: dict[str, float]
    on_share_exceeded: Literal["notify", "halt_member", "borrow_from_pool"] = "notify"


class TeamPolicy(BaseModel):
    trifecta_enforcement: Literal["strict", "warn", "off"] = "strict"
    max_hops: int = 5
    max_turns: int = 20
    termination_text: str = "DONE"


class TeamPackFrontmatter(BaseModel):
    name: str
    version: str
    manager: str | None = None
    members: list[str]
    edges: list[dict[str, Any]] = Field(default_factory=list)
    budget: TeamBudget
    policy: TeamPolicy = Field(default_factory=TeamPolicy)
    deployment: dict[str, str] = Field(default_factory=dict)


class TeamPackDocument(BaseModel):
    frontmatter: TeamPackFrontmatter
    body: str
    pack_dir: Path

    model_config = {"arbitrary_types_allowed": True}


def parse_team_pack(path: str | Path) -> TeamPackDocument:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{p}: missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{p}: missing YAML frontmatter")
    fm = TeamPackFrontmatter(**yaml.safe_load(parts[1]))
    return TeamPackDocument(frontmatter=fm, body=parts[2].strip(), pack_dir=p.parent)
