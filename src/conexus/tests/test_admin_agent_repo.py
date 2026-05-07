from pathlib import Path

import pytest

from conexus.web.admin.services.agent_repo import AgentSummary, list_agents, read_agent


def _seed_agent(root: Path, name: str, tools: list[str]) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    skill = (
        "---\n"
        f"name: {name}\n"
        "role: test\n"
        "goal: |\n  test\n"
        "llm:\n  provider: openai\n  model: gpt-4o-mini\n"
        f"tools: {tools}\n"
        "---\nbody"
    )
    (d / "SKILL.md").write_text(skill)
    (d / "tools.py").write_text("class T:\n    pass\n\ndef create_cli_tools(d):\n    return None, T()\n")


def test_list_agents_returns_summaries(tmp_path: Path) -> None:
    _seed_agent(tmp_path, "ana", ["foo", "bar"])
    _seed_agent(tmp_path, "pesq", [])
    agents = list_agents(tmp_path)
    by_name = {a.name: a for a in agents}
    assert isinstance(by_name["ana"], AgentSummary)
    assert by_name["ana"].tools_count == 2
    assert by_name["pesq"].tools_count == 0


def test_read_agent_returns_skill_and_tools(tmp_path: Path) -> None:
    _seed_agent(tmp_path, "ana", ["foo"])
    agent = read_agent(tmp_path, "ana")
    assert agent.skill.frontmatter.name == "ana"
    assert agent.tools_path.name == "tools.py"
    assert agent.skill.body.strip() == "body"


def test_read_agent_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_agent(tmp_path, "ghost")
