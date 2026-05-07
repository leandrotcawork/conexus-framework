"""List connectors enabled by an agent's skills: read from unified packs/registry.json."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from conexus.core.packs.registry import PacksRegistry


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
    reg = PacksRegistry.load(registry_path)
    enabled = {ref.split("@")[0] for ref in skill_refs}
    out: list[ConnectorEntry] = []
    for entry in reg.list(kind="connector"):
        if entry.id not in enabled:
            continue
        out.append(ConnectorEntry(
            id=entry.id,
            version=entry.version,
            label=entry.ui.label,
            icon=entry.ui.icon,
            category=entry.ui.category,
            description=entry.ui.description,
            server_url=entry.server_url,
            scopes=entry.scopes,
        ))
    return out
