"""Scan installed skill packs (per-agent or shared packs/) for Studio."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from conexus.core.skills.pack_loader import parse_skill_pack
from conexus.web.admin.services.tools_inspector import ToolMethod, scan_tools_file


@dataclass(frozen=True)
class InstalledPack:
    id: str
    version: str
    backend: str
    source_path: Path
    body: str
    methods: list[ToolMethod]


def _resolve(name: str, agent_dir: Path, packs_root: Path) -> Path | None:
    for base in (agent_dir / "skills", packs_root):
        candidate = base / name / "SKILL_PACK.md"
        if candidate.exists():
            return candidate
    return None


def scan_installed_packs(
    agent_dir: Path, *, packs_root: Path, skill_refs: list[str]
) -> list[InstalledPack]:
    out: list[InstalledPack] = []
    for ref in skill_refs:
        name = ref.split("@")[0]
        if "/" in name or "\\" in name or name.startswith("."):
            continue
        path = _resolve(name, agent_dir, packs_root)
        if path is None:
            continue
        doc = parse_skill_pack(path)
        tools_py = doc.pack_dir / "tools.py"
        methods = scan_tools_file(tools_py) if tools_py.exists() else []
        out.append(
            InstalledPack(
                id=doc.frontmatter.name,
                version=doc.frontmatter.version,
                backend=doc.frontmatter.backend.value,
                source_path=path,
                body=doc.body,
                methods=methods,
            )
        )
    return out
