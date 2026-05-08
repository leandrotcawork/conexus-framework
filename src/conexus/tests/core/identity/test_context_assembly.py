"""Identity context assembly — formats blocks + recent facts + wiki index for prompt injection."""
from __future__ import annotations

import pytest

from conexus.core.config.skill_loader import (
    BlockSpec,
    FactsSection,
    HistorySection,
    IdentitySection,
    WikiSection,
)
from conexus.core.identity.blocks import BlockStore
from conexus.core.identity.context import assemble_identity_context
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


@pytest.fixture
def setup(tmp_path):
    store = SqliteStore(str(tmp_path / "ctx.db"))
    store.init_db()
    wiki = WikiStore.local(tmp_path / "wiki")
    wiki.write("about.md", "# About")
    wiki.write("preferences/morning.md", "# Morning")
    blocks = BlockStore(store)
    blocks.set("ana", "user", "Leandro, dev pt-BR.", budget_chars=500)
    store.fact_set("ana", "wake_time", "6h")
    return store, wiki, blocks


def test_returns_empty_when_disabled(setup):
    store, wiki, blocks = setup
    cfg = IdentitySection(enabled=False)
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert ctx == ""


def test_includes_block_when_set(setup):
    store, wiki, blocks = setup
    cfg = IdentitySection(
        enabled=True,
        blocks={"user": BlockSpec(budget_chars=500)},
    )
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert "user" in ctx.lower()
    assert "Leandro, dev pt-BR." in ctx


def test_includes_recent_facts_when_inject_recent(setup):
    store, wiki, blocks = setup
    cfg = IdentitySection(
        enabled=True,
        facts=FactsSection(enabled=True, inject_recent=5),
    )
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert "wake_time" in ctx
    assert "6h" in ctx


def test_omits_facts_when_inject_recent_zero(setup):
    store, wiki, blocks = setup
    cfg = IdentitySection(
        enabled=True,
        facts=FactsSection(enabled=True, inject_recent=0),
    )
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert "wake_time" not in ctx


def test_includes_wiki_index_when_enabled(setup, tmp_path):
    store, wiki, blocks = setup
    cfg = IdentitySection(
        enabled=True,
        wiki=WikiSection(dir=str(tmp_path / "wiki"), inject_index=True),
    )
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert "about.md" in ctx
    assert "preferences/morning.md" in ctx


def test_omits_wiki_index_when_disabled(setup, tmp_path):
    store, wiki, blocks = setup
    cfg = IdentitySection(
        enabled=True,
        wiki=WikiSection(dir=str(tmp_path / "wiki"), inject_index=False),
    )
    ctx = assemble_identity_context("ana", cfg, store, wiki, blocks)
    assert "about.md" not in ctx
