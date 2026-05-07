"""End-to-end: SKILL.md with identity → handle_agent_message produces enriched system prompt."""
from __future__ import annotations

import textwrap

import pytest

from conexus.cli.identity_runtime import build_identity_runtime
from conexus.core.config.skill_loader import parse_skill_file
from conexus.core.identity.context import assemble_identity_context
from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def skill_path(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text(textwrap.dedent("""\
        ---
        name: ana
        role: secretary
        goal: help
        tools: []
        llm: {provider: gemini, model: gemini-2.5-flash}
        identity:
          enabled: true
          blocks:
            user:
              budget_chars: 500
              initial: "Leandro, dev pt-BR. Acorda 6h."
          facts:
            enabled: true
            inject_recent: 3
          wiki:
            dir: ./wiki
            inject_index: true
        ---
        # Ana
        Você é a Ana.
    """), encoding="utf-8")
    return p


def test_identity_e2e_assembles_full_context(skill_path, tmp_path):
    doc = parse_skill_file(skill_path)
    store = SqliteStore(str(tmp_path / "e2e.db"))
    store.init_db()

    runtime = build_identity_runtime(
        agent_id="ana",
        cfg=doc.frontmatter.identity,
        store=store,
        skill_dir=skill_path.parent,
    )
    assert runtime is not None

    runtime.tools.wiki_write(path="about.md", content="# About\nLeandro builds Conexus.")
    runtime.tools.memory_set(key="meeting_pref", value="morning")

    ctx = assemble_identity_context("ana", doc.frontmatter.identity, store, runtime.wiki, runtime.blocks)

    assert "Leandro, dev pt-BR. Acorda 6h." in ctx
    assert "meeting_pref" in ctx and "morning" in ctx
    assert "about.md" in ctx
