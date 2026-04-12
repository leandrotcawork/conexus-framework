"""SKILL.md parser. Splits YAML frontmatter from markdown body and validates it."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class LLMFallback(BaseModel):
    provider: str
    model: str


class LLMSection(BaseModel):
    provider: str
    model: str
    temperature: float = 0.4
    fallback: list[LLMFallback] = Field(default_factory=list)


class Schedule(BaseModel):
    kind: str
    cron: str


class BudgetSection(BaseModel):
    daily_usd: float
    monthly_usd: float
    on_exceed: str = "notify"


class SkillFrontmatter(BaseModel):
    name: str
    role: str
    language: str = "pt-BR"
    goal: str
    tools: list[str]
    llm: LLMSection
    schedules: list[Schedule] = Field(default_factory=list)
    budget: Optional[BudgetSection] = None


class SkillDocument(BaseModel):
    frontmatter: SkillFrontmatter
    body: str  # everything after the second '---'


def parse_skill_file(path: str | Path) -> SkillDocument:
    text = Path(path).read_text(encoding="utf-8")

    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML frontmatter")

    # Find the closing --- on its own line
    after_open = text[4:]
    try:
        close_index = after_open.index("\n---\n")
    except ValueError as e:
        raise ValueError(f"{path}: unterminated frontmatter") from e

    raw_frontmatter = after_open[:close_index]
    body = after_open[close_index + 5 :]

    data = yaml.safe_load(raw_frontmatter) or {}
    frontmatter = SkillFrontmatter.model_validate(data)
    return SkillDocument(frontmatter=frontmatter, body=body.strip())
