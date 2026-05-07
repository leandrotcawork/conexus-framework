from pathlib import Path
import json
import pytest
import yaml
from conexus.core.packs.installer import install_pack, uninstall_pack, InstallError


def _seed(tmp: Path) -> tuple[Path, Path]:
    """Return (agent_dir, packs_root). Stages a minimal valid pack and agent."""
    repo = tmp
    pack = repo / "packs" / "demo"
    pack.mkdir(parents=True)
    (pack / "SKILL_PACK.md").write_text(
        "---\nname: demo\nversion: 0.1.0\nbackend: python\n---\nbody"
    )
    (pack / "tools.py").write_text("class Tools:\n    def hi(self) -> str:\n        return 'hi'\n")

    agent = repo / "agents" / "ana"
    agent.mkdir(parents=True)
    (agent / "SKILL.md").write_text(
        "---\nname: ana\nrole: r\ngoal: g\nllm:\n  provider: openai\n  model: gpt-4o-mini\nskills: []\n---\nbody"
    )

    registry = repo / "packs" / "registry.json"
    registry.write_text(json.dumps({"version": "1.0", "entries": [
        {"id": "demo", "kind": "skill", "version": "0.1.0",
         "source": "packs/demo", "sha": "abc",
         "ui": {"label": "Demo", "icon": "i", "category": "c", "description": "d"}}
    ]}))

    return agent, repo / "packs"


def test_install_appends_to_skill_md(tmp_path: Path):
    agent_dir, packs_root = _seed(tmp_path)
    install_pack("demo", agent_dir=agent_dir, packs_root=packs_root,
                 registry_path=packs_root / "registry.json", allow_unsigned=True)
    fm = yaml.safe_load((agent_dir / "SKILL.md").read_text().split("---")[1])
    assert "demo" in fm["skills"]


def test_install_idempotent(tmp_path: Path):
    agent_dir, packs_root = _seed(tmp_path)
    install_pack("demo", agent_dir=agent_dir, packs_root=packs_root,
                 registry_path=packs_root / "registry.json", allow_unsigned=True)
    install_pack("demo", agent_dir=agent_dir, packs_root=packs_root,
                 registry_path=packs_root / "registry.json", allow_unsigned=True)
    fm = yaml.safe_load((agent_dir / "SKILL.md").read_text().split("---")[1])
    assert fm["skills"].count("demo") == 1


def test_install_rollback_on_failure(tmp_path: Path, monkeypatch):
    agent_dir, packs_root = _seed(tmp_path)
    skill_md_before = (agent_dir / "SKILL.md").read_text()

    import conexus.core.packs.installer as mod
    monkeypatch.setattr(mod, "_append_skill_ref", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(InstallError):
        install_pack("demo", agent_dir=agent_dir, packs_root=packs_root,
                     registry_path=packs_root / "registry.json", allow_unsigned=True)

    assert (agent_dir / "SKILL.md").read_text() == skill_md_before
    staged = list(agent_dir.glob(".install_stage_*"))
    assert staged == []


def test_uninstall_removes_from_skill_md(tmp_path: Path):
    agent_dir, packs_root = _seed(tmp_path)
    install_pack("demo", agent_dir=agent_dir, packs_root=packs_root,
                 registry_path=packs_root / "registry.json", allow_unsigned=True)
    uninstall_pack("demo", agent_dir=agent_dir)
    fm = yaml.safe_load((agent_dir / "SKILL.md").read_text().split("---")[1])
    assert "demo" not in (fm.get("skills") or [])


def test_install_rejects_unsigned_by_default(tmp_path: Path):
    agent_dir, packs_root = _seed(tmp_path)
    # sha is "abc" (non-empty) → succeeds with allow_unsigned=False
    install_pack("demo", agent_dir=agent_dir, packs_root=packs_root,
                 registry_path=packs_root / "registry.json", allow_unsigned=False)
    # Mutate registry to sha=="unsigned"
    (packs_root / "registry.json").write_text(json.dumps({"version": "1.0", "entries": [
        {"id": "demo", "kind": "skill", "version": "0.1.0", "source": "packs/demo",
         "sha": "unsigned",
         "ui": {"label": "Demo", "icon": "i", "category": "c", "description": "d"}}
    ]}))
    uninstall_pack("demo", agent_dir=agent_dir)
    with pytest.raises(InstallError, match="unsigned"):
        install_pack("demo", agent_dir=agent_dir, packs_root=packs_root,
                     registry_path=packs_root / "registry.json", allow_unsigned=False)
    # With override, succeeds
    install_pack("demo", agent_dir=agent_dir, packs_root=packs_root,
                 registry_path=packs_root / "registry.json", allow_unsigned=True)


def test_install_rejects_traversal_pack_id(tmp_path: Path):
    agent_dir, packs_root = _seed(tmp_path)
    for bad in ["../evil", "../../etc/passwd", ".hidden", "a\\b", ""]:
        with pytest.raises(InstallError, match="invalid pack_id"):
            install_pack(bad, agent_dir=agent_dir, packs_root=packs_root,
                         registry_path=packs_root / "registry.json", allow_unsigned=True)
