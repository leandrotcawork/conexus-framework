"""Connector pack manifest — parses SKILL_PACK.md + connector.json."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
from pydantic import BaseModel
from conexus.core.skills.pack_loader import parse_skill_pack, SkillPackDocument


class ConnectorUI(BaseModel):
    label: str
    icon: str = "plug"
    category: str = "Other"
    description: str = ""


class ConnectorDescriptor(BaseModel):
    server_url: str
    scopes: list[str]
    ui: ConnectorUI


@dataclass
class ConnectorPack:
    skill_pack: SkillPackDocument
    connector: ConnectorDescriptor


def parse_connector_pack(skill_pack_path: str | Path) -> ConnectorPack:
    sp = parse_skill_pack(skill_pack_path)
    cj = sp.pack_dir / "connector.json"
    if not cj.exists():
        raise FileNotFoundError(f"connector.json missing for pack {sp.frontmatter.name}: {cj}")
    desc = ConnectorDescriptor.model_validate(json.loads(cj.read_text()))
    return ConnectorPack(skill_pack=sp, connector=desc)
