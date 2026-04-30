# src/conexus/tests/test_framework_pack_loader.py
import pytest
from conexus.core.skills.pack_loader import parse_skill_pack, SkillPackBackend
from conexus.core.config.skill_loader import parse_skill_file

PACK_MD = """---
name: wiki
version: 1.0.0
backend: python
capabilities: [wiki_read, wiki_write]
data_classes:
  wiki_read: private_read
  wiki_write: external_write
budget_hint_usd: 0.01
prompts:
  - fragments/usage.md
---
Wiki skill body.
"""

def test_parse_skill_pack(tmp_path):
    (tmp_path / "SKILL_PACK.md").write_text(PACK_MD)
    doc = parse_skill_pack(tmp_path / "SKILL_PACK.md")
    assert doc.frontmatter.name == "wiki"
    assert doc.frontmatter.version == "1.0.0"
    assert doc.frontmatter.backend == SkillPackBackend.python
    assert doc.frontmatter.data_classes == {"wiki_read": "private_read", "wiki_write": "external_write"}
    assert doc.body.strip() == "Wiki skill body."
    assert doc.pack_dir == tmp_path

def test_parse_skill_pack_missing_frontmatter(tmp_path):
    (tmp_path / "SKILL_PACK.md").write_text("no frontmatter here")
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        parse_skill_pack(tmp_path / "SKILL_PACK.md")

SKILL_WITH_SKILLS = """---
name: ana
role: secretary
goal: help
tools: [wiki_read]
llm:
  provider: anthropic
  model: claude-sonnet-4-5
skills:
  - wiki@1.0.0
  - web-search@0.3.0
---
Body.
"""

def test_skill_frontmatter_skills_field(tmp_path):
    (tmp_path / "SKILL.md").write_text(SKILL_WITH_SKILLS)
    doc = parse_skill_file(tmp_path / "SKILL.md")
    assert doc.frontmatter.skills == ["wiki@1.0.0", "web-search@0.3.0"]

def test_skill_frontmatter_skills_optional(tmp_path):
    no_skills = SKILL_WITH_SKILLS.replace("skills:\n  - wiki@1.0.0\n  - web-search@0.3.0\n", "")
    (tmp_path / "SKILL.md").write_text(no_skills)
    doc = parse_skill_file(tmp_path / "SKILL.md")
    assert doc.frontmatter.skills == []
