"""Install a connector from registry into an agent folder + auto-append to skills:."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from conexus.core.connectors.registry import ConnectorRegistry

from .skill_writer import write_skill_md


def install_connector(
    *, agents_dir: Path, agent_name: str, connector_name: str, registry_path: Path
) -> None:
    registry = ConnectorRegistry.from_file(registry_path)
    entry = registry.get(connector_name)
    if entry is None:
        raise ValueError(f"connector not in registry: {connector_name}")

    agent = agents_dir / agent_name
    skill_path = agent / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"agent not found: {agent_name}")

    pack_dir = agent / "skills" / entry.name
    pack_dir.mkdir(parents=True, exist_ok=True)

    (pack_dir / "SKILL_PACK.md").write_text(
        "---\n"
        f"name: {entry.name}\nversion: \"{entry.version}\"\nbackend: mcp-http\n"
        "capabilities: []\ndata_classes: {}\n"
        "---\n"
        f"{entry.ui_description}\n"
    )
    (pack_dir / "connector.json").write_text(json.dumps({
        "server_url": entry.server_url,
        "scopes": entry.scopes,
        "ui": {
            "label": entry.ui_label,
            "icon": entry.ui_icon,
            "category": entry.ui_category,
            "description": entry.ui_description,
        },
    }, indent=2))

    raw = skill_path.read_text(encoding="utf-8")
    _, _, rest = raw.partition("---\n")
    front_raw, _, body = rest.partition("\n---\n")
    fm = yaml.safe_load(front_raw)
    skills: list[str] = list(fm.get("skills", []))
    ref = f"{entry.name}@{entry.version}"
    if ref not in skills:
        skills.append(ref)
        fm["skills"] = skills
        write_skill_md(skill_path, fm, body)
