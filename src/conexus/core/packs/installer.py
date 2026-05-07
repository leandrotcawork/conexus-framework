"""Pack installer — atomic edit of agent's SKILL.md skills: list."""
from __future__ import annotations

from pathlib import Path

import yaml

from conexus.core.packs.registry import PacksRegistry


class InstallError(RuntimeError):
    pass


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise InstallError("SKILL.md missing frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise InstallError("SKILL.md frontmatter unterminated")
    return yaml.safe_load(parts[1]) or {}, parts[2]


def _write_skill_md(path: Path, fm: dict, body: str) -> None:
    yml = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(f"---\n{yml}---{body}", encoding="utf-8")
    tmp.replace(path)  # atomic on POSIX + NTFS


def _append_skill_ref(skill_md: Path, pack_id: str) -> None:
    fm, body = _split_frontmatter(skill_md.read_text(encoding="utf-8"))
    skills = list(fm.get("skills") or [])
    if pack_id not in skills:
        skills.append(pack_id)
    fm["skills"] = skills
    _write_skill_md(skill_md, fm, body)


def _remove_skill_ref(skill_md: Path, pack_id: str) -> None:
    fm, body = _split_frontmatter(skill_md.read_text(encoding="utf-8"))
    skills = [s for s in (fm.get("skills") or []) if s != pack_id]
    fm["skills"] = skills
    _write_skill_md(skill_md, fm, body)


def install_pack(
    pack_id: str,
    *,
    agent_dir: Path,
    packs_root: Path,
    registry_path: Path,
    allow_unsigned: bool = False,
) -> None:
    reg = PacksRegistry.load(registry_path)
    try:
        entry = reg.get(pack_id)
    except Exception as e:
        raise InstallError(str(e)) from e

    if entry.sha == "unsigned" and not allow_unsigned:
        raise InstallError(
            f"pack '{pack_id}' is unsigned (sha='unsigned'); pass allow_unsigned=True to override"
        )

    pack_md = packs_root / pack_id / "SKILL_PACK.md"
    if not pack_md.exists():
        raise InstallError(f"pack source missing: {pack_md}")

    skill_md = agent_dir / "SKILL.md"
    if not skill_md.exists():
        raise InstallError(f"agent SKILL.md missing: {skill_md}")

    backup = skill_md.read_text(encoding="utf-8")
    try:
        _append_skill_ref(skill_md, pack_id)
    except Exception as e:
        skill_md.write_text(backup, encoding="utf-8")
        raise InstallError(f"install failed, rolled back: {e}") from e


def uninstall_pack(pack_id: str, *, agent_dir: Path) -> None:
    skill_md = agent_dir / "SKILL.md"
    if not skill_md.exists():
        raise InstallError(f"agent SKILL.md missing: {skill_md}")
    backup = skill_md.read_text(encoding="utf-8")
    try:
        _remove_skill_ref(skill_md, pack_id)
    except Exception as e:
        skill_md.write_text(backup, encoding="utf-8")
        raise InstallError(f"uninstall failed, rolled back: {e}") from e
