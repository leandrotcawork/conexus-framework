"""Tests for IdentitySection in SKILL.md frontmatter."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from conexus.core.config.skill_loader import (
    BlockSpec,
    HistorySection,
    IdentitySection,
    SkillFrontmatter,
    parse_skill_file,
)


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "SKILL.md"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_identity_section_defaults_disabled():
    fm = SkillFrontmatter(
        name="x", role="r", goal="g", tools=[],
        llm={"provider": "gemini", "model": "gemini-2.5-flash"},
    )
    assert fm.identity is None


def test_identity_section_full(tmp_path):
    skill = _write(tmp_path, """\
        ---
        name: ana
        role: secretary
        goal: help
        tools: []
        llm: {provider: gemini, model: gemini-2.5-flash}
        identity:
          enabled: true
          blocks:
            user: 500
            scratch: 200
          facts:
            enabled: true
            inject_recent: 5
          wiki:
            dir: ./wiki/ana
            inject_index: true
          history:
            budget_tokens: 4000
            keep_verbatim: 6
            summary_budget: 800
            trigger_pct: 0.80
        ---
        body
    """)
    doc = parse_skill_file(skill)
    ident = doc.frontmatter.identity
    assert ident is not None
    assert ident.enabled is True
    assert ident.blocks["user"].budget_chars == 500
    assert ident.facts.enabled is True
    assert ident.facts.inject_recent == 5
    assert ident.wiki.dir == "./wiki/ana"
    assert ident.wiki.inject_index is True
    assert ident.history.budget_tokens == 4000
    assert ident.history.keep_verbatim == 6


def test_identity_section_minimal(tmp_path):
    skill = _write(tmp_path, """\
        ---
        name: helper
        role: r
        goal: g
        tools: []
        llm: {provider: gemini, model: gemini-2.5-flash}
        identity:
          enabled: true
        ---
        body
    """)
    doc = parse_skill_file(skill)
    ident = doc.frontmatter.identity
    assert ident.enabled is True
    assert ident.blocks == {}
    assert ident.facts.enabled is False
    # Default factory: backward-compat — agents without explicit `wiki:` block
    # get a local wiki. To disable, set `wiki: null` explicitly in YAML.
    assert ident.wiki is not None
    assert ident.wiki.backend == "local"
    assert ident.history.budget_tokens == 4000  # default


def test_blocks_accept_int_or_dict(tmp_path):
    skill = _write(tmp_path, """\
        ---
        name: x
        role: r
        goal: g
        tools: []
        llm: {provider: gemini, model: gemini-2.5-flash}
        identity:
          enabled: true
          blocks:
            user: 500
            scratch: {budget_chars: 200, initial: "ready"}
        ---
        body
    """)
    doc = parse_skill_file(skill)
    blocks = doc.frontmatter.identity.blocks
    assert blocks["user"].budget_chars == 500
    assert blocks["user"].initial is None
    assert blocks["scratch"].budget_chars == 200
    assert blocks["scratch"].initial == "ready"
