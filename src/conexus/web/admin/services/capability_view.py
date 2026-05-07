"""Aggregate the 4 capability layers into one view for Studio."""
from __future__ import annotations

from pathlib import Path

from .connector_inspector import list_connectors_for_agent
from .identity_inspector import list_identity_tools
from .pack_inspector import scan_installed_packs
from .tools_inspector import scan_tools_file


def build_capability_view(
    *,
    agent_dir: Path,
    skill_refs: list[str],
    identity_enabled: bool,
    connector_registry: Path,
    packs_root: Path,
    model: str,
) -> dict:
    tools_py = agent_dir / "tools.py"
    native = scan_tools_file(tools_py) if tools_py.exists() else []
    identity = list_identity_tools(enabled=identity_enabled)
    packs = scan_installed_packs(agent_dir, packs_root=packs_root, skill_refs=skill_refs)
    connectors = list_connectors_for_agent(skill_refs, connector_registry)
    return {
        "native": native,
        "identity": identity,
        "packs": packs,
        "connectors": connectors,
    }
