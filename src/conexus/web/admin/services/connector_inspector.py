"""List connectors enabled by an agent's skills: list, return display metadata."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConnectorEntry:
    id: str
    version: str
    label: str
    icon: str
    category: str
    description: str
    server_url: str
    scopes: list[str]


def list_connectors_for_agent(
    skill_refs: list[str], registry_path: Path
) -> list[ConnectorEntry]:
    if not registry_path.exists():
        return []
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    enabled = {ref.split("@")[0] for ref in skill_refs}
    out: list[ConnectorEntry] = []
    for c in data.get("connectors", []):
        if c["name"] not in enabled:
            continue
        ui = c.get("ui", {})
        out.append(ConnectorEntry(
            id=c["name"],
            version=c.get("version", "unknown"),
            label=ui.get("label", c["name"]),
            icon=ui.get("icon", "plug"),
            category=ui.get("category", "Other"),
            description=ui.get("description", ""),
            server_url=c.get("server_url", ""),
            scopes=c.get("scopes", []),
        ))
    return out
