"""List + read agents from filesystem. Pure functions over Path."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from conexus.core.config.skill_loader import SkillDocument, parse_skill_file


@dataclass(frozen=True)
class AgentSummary:
    name: str
    role: str
    llm_model: str
    tools_count: int
    identity_enabled: bool


@dataclass(frozen=True)
class AgentDetail:
    """`skill` is a SkillDocument with .frontmatter + .body."""
    name: str
    skill: SkillDocument
    skill_path: Path
    tools_path: Path


def _agent_dirs(agents_dir: Path) -> list[Path]:
    if not agents_dir.exists():
        return []
    return sorted(d for d in agents_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists())


def list_agents(agents_dir: Path) -> list[AgentSummary]:
    out: list[AgentSummary] = []
    for d in _agent_dirs(agents_dir):
        try:
            doc = parse_skill_file(d / "SKILL.md")
        except Exception:  # noqa: BLE001
            continue
        fm = doc.frontmatter
        out.append(
            AgentSummary(
                name=fm.name,
                role=fm.role,
                llm_model=fm.llm.model,
                tools_count=len(fm.tools),
                identity_enabled=bool(fm.identity and fm.identity.enabled),
            )
        )
    return out


def read_agent(agents_dir: Path, name: str) -> AgentDetail:
    d = agents_dir / name
    skill_path = d / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"agent not found: {name}")
    doc = parse_skill_file(skill_path)
    return AgentDetail(
        name=doc.frontmatter.name, skill=doc, skill_path=skill_path, tools_path=d / "tools.py"
    )
