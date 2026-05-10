from pathlib import Path
from conexus.core.skills.skill_resolver import SkillLoader
from conexus.core.agent_registry import AgentRegistry


def _make_pack(root: Path, name: str) -> None:
    p = root / name
    p.mkdir(parents=True)
    (p / "SKILL_PACK.md").write_text(
        "---\nname: " + name + "\nversion: 0.1.0\nbackend: python\n---\nbody"
    )
    (p / "tools.py").write_text(
        "class Tools:\n    def hi(self) -> str:\n        return 'hi'\n"
    )


def test_resolver_uses_shared_packs_when_per_agent_missing(tmp_path: Path):
    agent_dir = tmp_path / "agents" / "ana"
    agent_dir.mkdir(parents=True)
    packs_root = tmp_path / "packs"
    _make_pack(packs_root, "shared_pack")
    registry = AgentRegistry()
    loader = SkillLoader(agent_dir, registry, "ana", packs_root=packs_root)
    fragment, tags = loader.load(["shared_pack"])
    assert "body" in fragment


def test_resolver_per_agent_wins_over_shared(tmp_path: Path):
    agent_dir = tmp_path / "agents" / "ana"
    _make_pack(agent_dir / "skills", "demo")
    packs_root = tmp_path / "packs"
    _make_pack(packs_root, "demo")
    (packs_root / "demo" / "SKILL_PACK.md").write_text(
        "---\nname: demo\nversion: 0.1.0\nbackend: python\n---\nSHARED_BODY"
    )
    (agent_dir / "skills" / "demo" / "SKILL_PACK.md").write_text(
        "---\nname: demo\nversion: 0.1.0\nbackend: python\n---\nPER_AGENT_BODY"
    )
    registry = AgentRegistry()
    loader = SkillLoader(agent_dir, registry, "ana", packs_root=packs_root)
    fragment, _ = loader.load(["demo"])
    assert "PER_AGENT_BODY" in fragment
    assert "SHARED_BODY" not in fragment
