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
