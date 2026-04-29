import sqlite3
from pathlib import Path


from conexus.core.memory.sqlite_store import SqliteStore


def test_init_db_creates_all_tables(tmp_db_path: Path):
    store = SqliteStore(tmp_db_path)
    store.init_db()

    conn = sqlite3.connect(tmp_db_path)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()

    expected = {
        "facts", "todos", "chat_history",
        "ping_log", "llm_usage", "failed_sends",
    }
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


def _fresh(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    return store


def test_facts_roundtrip(tmp_db_path):
    store = _fresh(tmp_db_path)
    store.fact_set("timezone", "America/Sao_Paulo")
    assert store.fact_get("timezone") == "America/Sao_Paulo"

    store.fact_set("timezone", "UTC")
    assert store.fact_get("timezone") == "UTC"
    assert store.fact_get("nonexistent") is None

    facts = store.facts_list()
    assert {f["key"] for f in facts} == {"timezone"}


def test_todos_lifecycle(tmp_db_path):
    store = _fresh(tmp_db_path)
    todo_id = store.todo_add("buy milk", due_iso="2026-04-12T18:00:00-03:00")
    assert todo_id > 0

    open_todos = store.todos_list("open")
    assert len(open_todos) == 1
    assert open_todos[0]["text"] == "buy milk"

    store.todo_mark_done(todo_id)
    assert store.todos_list("open") == []
    done_todos = store.todos_list("done")
    assert len(done_todos) == 1


def test_chat_history_per_agent(tmp_db_path):
    store = _fresh(tmp_db_path)
    store.chat_append("ana", "user", "olá")
    store.chat_append("ana", "assistant", "oi!")
    store.chat_append("researcher", "user", "news today")

    ana_history = store.chat_recent("ana", limit=10)
    assert len(ana_history) == 2
    assert ana_history[-1]["content"] == "oi!"


def test_ping_log_idempotency(tmp_db_path):
    store = _fresh(tmp_db_path)
    assert store.ping_was_sent("briefing", "2026-04-12", "ana") is False
    store.ping_mark_pending("briefing", "2026-04-12", "ana")
    assert store.ping_was_sent("briefing", "2026-04-12", "ana") is False  # still pending
    store.ping_mark_sent("briefing", "2026-04-12", "ana")
    assert store.ping_was_sent("briefing", "2026-04-12", "ana") is True
