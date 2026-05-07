from pathlib import Path
import pytest
from conexus.web.admin.services.pack_inspector import scan_installed_packs, InstalledPack


def test_scan_empty_agent(tmp_path: Path):
    agent_dir = tmp_path / "agents" / "ana"
    agent_dir.mkdir(parents=True)
    (agent_dir / "SKILL.md").write_text("---\nname: ana\nskills: []\n---\n")
    result = scan_installed_packs(agent_dir, packs_root=tmp_path / "packs", skill_refs=[])
    assert result == []


def test_scan_finds_per_agent_pack(tmp_path: Path):
    agent_dir = tmp_path / "agents" / "ana"
    pack_dir = agent_dir / "skills" / "demo"
    pack_dir.mkdir(parents=True)
    (pack_dir / "SKILL_PACK.md").write_text(
        "---\nname: demo\nversion: 0.1.0\nbackend: python\n---\nbody"
    )
    result = scan_installed_packs(agent_dir, packs_root=tmp_path / "packs", skill_refs=["demo"])
    assert len(result) == 1
    assert result[0].id == "demo"
    assert result[0].version == "0.1.0"


def test_scan_falls_back_to_shared_packs(tmp_path: Path):
    agent_dir = tmp_path / "agents" / "ana"
    agent_dir.mkdir(parents=True)
    pack_dir = tmp_path / "packs" / "shared"
    pack_dir.mkdir(parents=True)
    (pack_dir / "SKILL_PACK.md").write_text(
        "---\nname: shared\nversion: 0.2.0\nbackend: python\n---\n"
    )
    result = scan_installed_packs(agent_dir, packs_root=tmp_path / "packs", skill_refs=["shared"])
    assert len(result) == 1
    assert result[0].id == "shared"


def test_scan_skips_unresolved_refs(tmp_path: Path):
    agent_dir = tmp_path / "agents" / "ana"
    agent_dir.mkdir(parents=True)
    result = scan_installed_packs(
        agent_dir, packs_root=tmp_path / "packs", skill_refs=["does-not-exist"]
    )
    assert result == []
