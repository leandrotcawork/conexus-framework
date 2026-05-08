"""Identity prompt template assembly."""
from __future__ import annotations

from conexus.core.identity.prompt import (
    DEFAULT_MEMORY_PROMPT_PT_BR,
    load_memory_prompt,
)


def test_default_prompt_has_three_layers():
    p = DEFAULT_MEMORY_PROMPT_PT_BR
    assert "memory_set" in p
    assert "wiki_write" in p
    assert "notes" in p.lower()
    assert p.startswith("## Memória")


def test_load_returns_default_when_no_override():
    assert load_memory_prompt(None, None) == DEFAULT_MEMORY_PROMPT_PT_BR


def test_load_reads_override_file(tmp_path):
    f = tmp_path / "custom.md"
    f.write_text("custom guidance", encoding="utf-8")
    assert load_memory_prompt(str(f), tmp_path) == "custom guidance"


def test_load_resolves_relative_to_skill_dir(tmp_path):
    (tmp_path / "p.md").write_text("X", encoding="utf-8")
    assert load_memory_prompt("./p.md", tmp_path) == "X"
