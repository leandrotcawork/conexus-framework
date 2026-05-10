"""Chat summaries — rolling per-(agent, chat) compaction state."""
from __future__ import annotations

import pytest

from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(":memory:")
    s.init_db()
    return s


def test_summary_get_returns_none_when_missing(store):
    assert store.summary_get("ana", "chat-1") is None


def test_summary_set_and_get(store):
    store.summary_set("ana", "chat-1", "User asked about Conexus.", covers_until_msg_id=42, token_count=150)
    s = store.summary_get("ana", "chat-1")
    assert s["summary_text"] == "User asked about Conexus."
    assert s["covers_until_msg_id"] == 42
    assert s["token_count"] == 150


def test_summary_replace_on_update(store):
    store.summary_set("ana", "chat-1", "first", covers_until_msg_id=10, token_count=10)
    store.summary_set("ana", "chat-1", "second", covers_until_msg_id=20, token_count=20)
    s = store.summary_get("ana", "chat-1")
    assert s["summary_text"] == "second"
    assert s["covers_until_msg_id"] == 20
