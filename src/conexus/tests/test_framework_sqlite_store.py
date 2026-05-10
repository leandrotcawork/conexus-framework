import tempfile
import threading
from pathlib import Path

from conexus.core.memory.sqlite_store import SqliteStore


def _fresh():
    store = SqliteStore(":memory:")
    store.init_db()
    return store


def test_init_db_creates_all_tables():
    store = _fresh()
    tables = {row[0] for row in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    expected = {
        "facts", "todos", "chat_history",
        "ping_log", "llm_usage", "failed_sends",
    }
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


def test_facts_roundtrip():
    store = _fresh()
    store.fact_set("test", "timezone", "America/Sao_Paulo")
    assert store.fact_get("test", "timezone") == "America/Sao_Paulo"

    store.fact_set("test", "timezone", "UTC")
    assert store.fact_get("test", "timezone") == "UTC"
    assert store.fact_get("test", "nonexistent") is None

    facts = store.facts_list("test")
    assert {f["key"] for f in facts} == {"timezone"}


def test_todos_lifecycle():
    store = _fresh()
    todo_id = store.todo_add("buy milk", due_iso="2026-04-12T18:00:00-03:00")
    assert todo_id > 0

    open_todos = store.todos_list("open")
    assert len(open_todos) == 1
    assert open_todos[0]["text"] == "buy milk"

    store.todo_mark_done(todo_id)
    assert store.todos_list("open") == []
    done_todos = store.todos_list("done")
    assert len(done_todos) == 1


def test_chat_history_per_agent():
    store = _fresh()
    store.chat_append("ana", "user", "olá")
    store.chat_append("ana", "assistant", "oi!")
    store.chat_append("researcher", "user", "news today")

    ana_history = store.chat_recent("ana", limit=10)
    assert len(ana_history) == 2
    assert ana_history[-1]["content"] == "oi!"


def test_wal_enabled_on_file_backed_store():
    with tempfile.TemporaryDirectory() as td:
        store = SqliteStore(Path(td) / "x.db")
        store.init_db()
        with store.connect() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode.lower() == "wal"
            sync = conn.execute("PRAGMA synchronous").fetchone()[0]
            assert sync == 1  # NORMAL == 1
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert busy == 5000


def test_memory_store_skips_wal_but_sets_pragmas():
    store = SqliteStore(":memory:")
    store.init_db()
    with store.connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() in ("memory", "delete")  # WAL unsupported on :memory:
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert busy == 5000


def test_concurrent_read_during_write_does_not_block():
    with tempfile.TemporaryDirectory() as td:
        store = SqliteStore(Path(td) / "y.db")
        store.init_db()
        store.fact_set("a", "k", "v")

        write_done = threading.Event()
        errors: list[Exception] = []

        def writer():
            try:
                for i in range(20):
                    store.fact_set("a", f"k{i}", str(i))
            except Exception as e:
                errors.append(e)
            finally:
                write_done.set()

        def reader():
            while not write_done.is_set():
                store.fact_get("a", "k")

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        assert not errors, f"writer failed: {errors}"
        assert write_done.is_set()


def test_ping_log_idempotency():
    store = _fresh()
    assert store.ping_was_sent("briefing", "2026-04-12", "ana") is False
    store.ping_mark_pending("briefing", "2026-04-12", "ana")
    assert store.ping_was_sent("briefing", "2026-04-12", "ana") is False
    store.ping_mark_sent("briefing", "2026-04-12", "ana")
    assert store.ping_was_sent("briefing", "2026-04-12", "ana") is True
