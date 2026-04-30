"""SKILL_PACK.md parser — pip-installable skill package descriptor."""
from __future__ import annotations
from enum import Enum
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field


class SkillPackBackend(str, Enum):
    python = "python"
    mcp_stdio = "mcp-stdio"
    mcp_http = "mcp-http"


class SkillPackFrontmatter(BaseModel):
    name: str
    version: str
    backend: SkillPackBackend = SkillPackBackend.python
    capabilities: list[str] = Field(default_factory=list)
    data_classes: dict[str, str] = Field(default_factory=dict)
    budget_hint_usd: Optional[float] = None
    prompts: list[str] = Field(default_factory=list)


class SkillPackDocument(BaseModel):
    frontmatter: SkillPackFrontmatter
    body: str
    pack_dir: Path


def parse_skill_pack(path: str | Path) -> SkillPackDocument:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML frontmatter")
    after_open = text[4:]
    try:
        close_index = after_open.index("\n---\n")
    except ValueError as e:
        raise ValueError(f"{path}: unterminated frontmatter") from e
    raw = after_open[:close_index]
    body = after_open[close_index + 5:]
    data = yaml.safe_load(raw) or {}
    fm = SkillPackFrontmatter.model_validate(data)
    return SkillPackDocument(frontmatter=fm, body=body.strip(), pack_dir=path.parent)
