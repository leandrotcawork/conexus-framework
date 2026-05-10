"""Facts table must be scoped per agent_id."""
from __future__ import annotations

import pytest

from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(":memory:")
    s.init_db()
    return s


def test_facts_isolated_per_agent(store):
    store.fact_set("ana", "wake_time", "6h")
    store.fact_set("helper", "wake_time", "8h")
    assert store.fact_get("ana", "wake_time") == "6h"
    assert store.fact_get("helper", "wake_time") == "8h"


def test_facts_list_scoped(store):
    store.fact_set("ana", "k1", "v1")
    store.fact_set("ana", "k2", "v2")
    store.fact_set("helper", "k3", "v3")
    ana_facts = store.facts_list("ana")
    assert len(ana_facts) == 2
    assert {f["key"] for f in ana_facts} == {"k1", "k2"}
    helper_facts = store.facts_list("helper")
    assert len(helper_facts) == 1


def test_facts_recent_returns_newest_first(store):
    store.fact_set("ana", "old", "v")
    store.fact_set("ana", "new", "v")
    recent = store.facts_recent("ana", limit=10)
    assert recent[0]["key"] == "new"
    assert recent[1]["key"] == "old"


def test_facts_migration_preserves_legacy_rows(tmp_path):
    """Pre-existing global facts rows (no agent_id) get bucketed to '_legacy'."""
    import sqlite3
    db_path = tmp_path / "legacy.db"
    # Simulate old schema
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE facts (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO facts (key, value, updated_at) VALUES ('legacy_k', 'legacy_v', '2026-01-01');
    """)
    conn.commit()
    conn.close()
    # Now run init_db — should migrate
    store = SqliteStore(str(db_path))
    store.init_db()
    assert store.fact_get("_legacy", "legacy_k") == "legacy_v"
