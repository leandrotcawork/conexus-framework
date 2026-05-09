"""Built-in IdentityTools: memory_*, wiki_*, block_* methods auto-registered when identity.enabled."""
from __future__ import annotations

from pathlib import Path

import pytest

from conexus.core.identity.tools import IdentityTools
from conexus.core.identity.blocks import BlockStore
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


@pytest.fixture
def deps(tmp_path):
    store = SqliteStore(":memory:")
    store.init_db()
    wiki = WikiStore.local(tmp_path / "wiki")
    blocks = BlockStore(store)
    tools = IdentityTools(
        agent_id="ana",
        store=store,
        wiki=wiki,
        blocks=blocks,
        block_specs={"user": 500, "scratch": 200},
    )
    return tools, store, wiki, blocks


def test_memory_set_and_get(deps):
    tools, _, _, _ = deps
    tools.memory_set(key="wake_time", value="6h")
    assert tools.memory_get(key="wake_time") == {"key": "wake_time", "value": "6h"}


def test_memory_list_facts_returns_recent(deps):
    tools, _, _, _ = deps
    tools.memory_set(key="a", value="1")
    tools.memory_set(key="b", value="2")
    facts = tools.memory_list_facts()
    assert {f["key"] for f in facts} == {"a", "b"}


def test_block_get_set(deps):
    tools, _, _, _ = deps
    tools.block_set(name="user", content="Leandro, dev pt-BR.")
    assert tools.block_get(name="user") == "Leandro, dev pt-BR."


def test_block_set_unknown_block_rejected(deps):
    tools, _, _, _ = deps
    with pytest.raises(ValueError, match="not declared"):
        tools.block_set(name="undeclared", content="x")


def test_wiki_write_read(deps, tmp_path):
    tools, _, _, _ = deps
    tools.wiki_write(path="about.md", content="# About\nLeandro builds Conexus.")
    result = tools.wiki_read(path="about.md")
    assert result["ok"] is True
    assert "Leandro builds Conexus" in result["content"]


def test_wiki_list(deps):
    tools, _, _, _ = deps
    tools.wiki_write(path="a.md", content="a")
    tools.wiki_write(path="b.md", content="b")
    files = tools.wiki_list()
    assert "a.md" in files and "b.md" in files
