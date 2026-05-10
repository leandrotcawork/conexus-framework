"""SKILL.md parser. Splits YAML frontmatter from markdown body and validates it."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator


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


class BlockSpec(BaseModel):
    """A core-memory block — small mutable text buffer pinned in system prompt."""
    budget_chars: int
    initial: str | None = None

    @classmethod
    def coerce(cls, v):
        # Allow `user: 500` (int) shorthand for `user: {budget_chars: 500}`
        if isinstance(v, int):
            return cls(budget_chars=v)
        return v


class FactsSection(BaseModel):
    enabled: bool = False
    inject_recent: int = 0  # 0 = tool-pull only


class WikiSection(BaseModel):
    backend: str = "local"
    dir: str = "./wiki"
    inject_index: bool = True
    repo: str | None = None  # Phase 2 (github_app)

    @field_validator("backend")
    @classmethod
    def _validate_backend(cls, v: str) -> str:
        if v not in {"local", "github_app"}:
            raise ValueError(f"unknown wiki backend: {v!r}")
        return v


class HistorySection(BaseModel):
    budget_tokens: int = 4000
    keep_verbatim: int = 6
    summary_budget: int = 800
    trigger_pct: float = 0.80


class IdentitySection(BaseModel):
    enabled: bool = False
    blocks: dict[str, BlockSpec] = Field(default_factory=dict)
    facts: FactsSection = Field(default_factory=FactsSection)
    # Default to local wiki so existing agents (e.g. anna) keep working without
    # adding an explicit `identity.wiki` block. Set to None only via explicit
    # YAML `wiki: null`.
    wiki: WikiSection | None = Field(default_factory=WikiSection)
    history: HistorySection = Field(default_factory=HistorySection)
    prompt_override: str | None = None

    @field_validator("blocks", mode="before")
    @classmethod
    def _coerce_blocks(cls, v):
        if isinstance(v, dict):
            return {k: BlockSpec.coerce(val) for k, val in v.items()}
        return v


class SkillFrontmatter(BaseModel):
    name: str
    role: str
    language: str = "pt-BR"
    prefix: str | None = None
    goal: str
    tools: list[str]
    llm: LLMSection
    llm_synthesis: LLMSection | None = None
    schedules: list[Schedule] = Field(default_factory=list)
    budget: Optional[BudgetSection] = None
    skills: list[str] = Field(default_factory=list)
    identity: IdentitySection | None = None


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
