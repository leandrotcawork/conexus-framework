from pathlib import Path

import pytest

from core.config.skill_loader import parse_skill_file


SAMPLE = """---
name: Ana
role: Secretária pessoal
language: pt-BR
goal: Ajudar o Leandro
tools:
  - calendar_list_events
  - memory_get
llm:
  provider: gemini
  model: gemini-2.0-flash
  temperature: 0.4
  fallback:
    - { provider: openai, model: gpt-4o-mini }
schedules:
  - { kind: briefing, cron: "0 7 * * *" }
budget:
  daily_usd: 0.25
  monthly_usd: 6.00
  on_exceed: notify
---

# Ana

## Sobre você
Você é a Ana.
"""


def test_parses_valid_skill(tmp_path: Path):
    p = tmp_path / "SKILL.md"
    p.write_text(SAMPLE, encoding="utf-8")

    doc = parse_skill_file(p)
    assert doc.frontmatter.name == "Ana"
    assert doc.frontmatter.language == "pt-BR"
    assert doc.frontmatter.llm.provider == "gemini"
    assert doc.frontmatter.llm.fallback[0].model == "gpt-4o-mini"
    assert doc.frontmatter.budget.daily_usd == 0.25
    assert "Sobre você" in doc.body


def test_rejects_missing_frontmatter(tmp_path: Path):
    p = tmp_path / "SKILL.md"
    p.write_text("just markdown", encoding="utf-8")
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        parse_skill_file(p)


def test_rejects_unterminated_frontmatter(tmp_path: Path):
    p = tmp_path / "SKILL.md"
    p.write_text("---\nname: Ana\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unterminated frontmatter"):
        parse_skill_file(p)


def test_rejects_missing_required_field(tmp_path: Path):
    p = tmp_path / "SKILL.md"
    p.write_text("---\nname: Ana\n---\nbody", encoding="utf-8")
    with pytest.raises(Exception):  # pydantic ValidationError
        parse_skill_file(p)
