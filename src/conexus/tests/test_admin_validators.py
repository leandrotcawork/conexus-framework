from pathlib import Path

from conexus.web.admin.services.validators import validate_agent, ValidationResult


def _seed(root: Path, name="ana", tools=None, body="x"):
    tools = tools if tools is not None else ["foo"]
    d = root / name
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    (d / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\nrole: test\ngoal: |\n  goal\n"
        "llm:\n  provider: openai\n  model: gpt-4o-mini\n  temperature: 0.4\n"
        f"tools: {tools}\n---\n{body}"
    )
    (d / "tools.py").write_text(
        "class Tools:\n    def foo(self) -> dict: return {}\n\n"
        "def create_cli_tools(d): return None, Tools()\n"
    )


def test_valid_agent_passes(tmp_path: Path) -> None:
    _seed(tmp_path)
    res = validate_agent(tmp_path, "ana")
    assert res.ok and not res.errors


def test_unknown_tool_in_skill_md_blocks(tmp_path: Path) -> None:
    _seed(tmp_path, tools=["foo", "ghost"])
    res = validate_agent(tmp_path, "ana")
    assert not res.ok
    assert any("ghost" in e for e in res.errors)


def test_short_prompt_warns(tmp_path: Path) -> None:
    _seed(tmp_path, body="hi")
    res = validate_agent(tmp_path, "ana")
    assert res.ok
    assert any("prompt" in w.lower() for w in res.warnings)


def test_unimportable_tools_py_blocks(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "ana" / "tools.py").write_text("syntax !!! error")
    res = validate_agent(tmp_path, "ana")
    assert not res.ok
    assert any("import" in e.lower() or "syntax" in e.lower() for e in res.errors)


def test_identity_tools_match_real_class() -> None:
    """Drift guard: IDENTITY_TOOLS must equal IdentityTools public method set."""
    from conexus.core.identity.tools import IdentityTools
    from conexus.web.admin.services.validators import IDENTITY_TOOLS

    real = {
        n for n in dir(IdentityTools)
        if not n.startswith("_") and callable(getattr(IdentityTools, n))
    }
    assert IDENTITY_TOOLS == real
