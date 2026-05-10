"""Tests for skill_loader with dual-LLM and prefix support."""

from pathlib import Path
from conexus.core.config.skill_loader import parse_skill_file


def test_parse_skill_with_synthesis_llm(tmp_path: Path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: Pesquisador\n"
        "role: Knowledge researcher\n"
        "language: pt-BR\n"
        "prefix: pesq\n"
        "goal: Research and build knowledge wiki\n"
        "tools:\n"
        "  - wiki_read\n"
        "  - web_search\n"
        "llm:\n"
        "  provider: gemini\n"
        "  model: gemini-2.5-flash\n"
        "  temperature: 0.3\n"
        "llm_synthesis:\n"
        "  provider: deepseek\n"
        "  model: deepseek-reasoner\n"
        "  temperature: 0.2\n"
        "budget:\n"
        "  daily_usd: 0.15\n"
        "  monthly_usd: 4.50\n"
        "  on_exceed: notify\n"
        "---\n"
        "# System prompt body\n"
    )
    doc = parse_skill_file(skill_md)
    assert doc.frontmatter.name == "Pesquisador"
    assert doc.frontmatter.prefix == "pesq"
    assert doc.frontmatter.llm.provider == "gemini"
    assert doc.frontmatter.llm_synthesis is not None
    assert doc.frontmatter.llm_synthesis.provider == "deepseek"
    assert doc.frontmatter.llm_synthesis.model == "deepseek-reasoner"
    assert doc.frontmatter.llm_synthesis.temperature == 0.2


def test_parse_skill_without_synthesis_llm(tmp_path: Path):
    """Ana's SKILL.md has no llm_synthesis — should still parse fine."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: Ana\n"
        "role: Secretary\n"
        "goal: Help Leandro\n"
        "tools:\n"
        "  - memory_get\n"
        "llm:\n"
        "  provider: gemini\n"
        "  model: gemini-2.5-flash\n"
        "---\n"
        "# Ana prompt\n"
    )
    doc = parse_skill_file(skill_md)
    assert doc.frontmatter.llm_synthesis is None
    assert doc.frontmatter.prefix is None


def test_wiki_section_accepts_backend_field():
    from conexus.core.config.skill_loader import WikiSection
    s = WikiSection(backend="local", dir="./wiki")
    assert s.backend == "local"
    assert s.dir == "./wiki"


def test_wiki_section_defaults_backend_to_local():
    from conexus.core.config.skill_loader import WikiSection
    s = WikiSection(dir="./wiki")
    assert s.backend == "local"


def test_wiki_section_rejects_unknown_backend():
    import pytest
    from conexus.core.config.skill_loader import WikiSection
    with pytest.raises(ValueError):
        WikiSection(backend="ftp", dir="./wiki")


def test_identity_section_accepts_prompt_override():
    from conexus.core.config.skill_loader import IdentitySection
    s = IdentitySection(enabled=True, prompt_override="./custom.md")
    assert s.prompt_override == "./custom.md"


def test_identity_section_default_wiki_is_local():
    """Backward compat: agents without identity.wiki block still get local wiki."""
    from conexus.core.config.skill_loader import IdentitySection
    s = IdentitySection(enabled=True)
    assert s.wiki is not None
    assert s.wiki.backend == "local"
    assert s.wiki.dir == "./wiki"


def test_anna_skill_parses_with_default_wiki():
    """Anna's SKILL.md has identity.enabled but no wiki block — must still load."""
    from conexus.core.config.skill_loader import parse_skill_file
    p = Path("agents/anna/SKILL.md")
    if not p.exists():
        import pytest
        pytest.skip("anna SKILL.md not present")
    doc = parse_skill_file(str(p))
    assert doc.frontmatter.identity is not None
    assert doc.frontmatter.identity.enabled is True
    assert doc.frontmatter.identity.wiki is not None
    assert doc.frontmatter.identity.wiki.backend == "local"
