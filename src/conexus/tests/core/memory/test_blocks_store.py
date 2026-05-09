"""Identity blocks: char-budgeted mutable text buffers per (agent_id, name)."""
from __future__ import annotations

import pytest

from conexus.core.identity.blocks import BlockStore, BlockOverBudgetError
from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(":memory:")
    s.init_db()
    return BlockStore(s)


def test_block_set_and_get(store):
    store.set("ana", "user", "Leandro, dev pt-BR.", budget_chars=500)
    assert store.get("ana", "user") == "Leandro, dev pt-BR."


def test_block_returns_none_when_missing(store):
    assert store.get("ana", "missing") is None


def test_block_isolated_per_agent(store):
    store.set("ana", "user", "Leandro", budget_chars=100)
    store.set("helper", "user", "Other", budget_chars=100)
    assert store.get("ana", "user") == "Leandro"
    assert store.get("helper", "user") == "Other"


def test_block_rejects_over_budget(store):
    with pytest.raises(BlockOverBudgetError):
        store.set("ana", "user", "x" * 101, budget_chars=100)


def test_block_list_for_agent(store):
    store.set("ana", "user", "u", budget_chars=100)
    store.set("ana", "scratch", "s", budget_chars=100)
    blocks = store.list("ana")
    assert {b["name"] for b in blocks} == {"user", "scratch"}
