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


# ----- ping_log tri-state tests -----

def test_ping_get_state_pending():
    store = _fresh()
    assert store.ping_get_state("job", "r1", "ana") is None
    store.ping_mark_pending("job", "r1", "ana")
    # first pending call: attempts=1, state=pending
    row = store.conn.execute("SELECT attempts FROM ping_log WHERE kind='job'").fetchone()
    assert row["attempts"] == 1
    assert store.ping_get_state("job", "r1", "ana") == "pending"


def test_ping_get_state_sent():
    store = _fresh()
    store.ping_mark_pending("job", "r1", "ana")
    store.ping_mark_sent("job", "r1", "ana")
    assert store.ping_get_state("job", "r1", "ana") == "sent"
    assert store.ping_was_sent("job", "r1", "ana") is True


def test_ping_mark_failed_sets_failure_state():
    """ping_mark_failed sets failed_at/last_error; attempts incremented only by ping_mark_pending."""
    store = _fresh()
    store.ping_mark_pending("job", "r1", "ana")  # attempts=1
    store.ping_mark_failed("job", "r1", "ana", "timeout")
    row = store.conn.execute(
        "SELECT attempts, failed_at, last_error FROM ping_log WHERE kind='job' AND ref_id='r1' AND agent_name='ana'"
    ).fetchone()
    assert row["attempts"] == 1  # NOT incremented by mark_failed
    assert row["failed_at"] is not None
    assert row["last_error"] == "timeout"
    assert store.ping_get_state("job", "r1", "ana") == "failed"
    assert store.ping_was_sent("job", "r1", "ana") is False


def test_ping_mark_sent_after_failed_clears_failure():
    store = _fresh()
    store.ping_mark_pending("job", "r1", "ana")
    store.ping_mark_failed("job", "r1", "ana", "err")
    store.ping_mark_sent("job", "r1", "ana")
    assert store.ping_get_state("job", "r1", "ana") == "sent"
    row = store.conn.execute(
        "SELECT failed_at, last_error FROM ping_log WHERE kind='job' AND ref_id='r1' AND agent_name='ana'"
    ).fetchone()
    assert row["failed_at"] is None
    assert row["last_error"] is None


def test_ping_dead_letter_cap_at_three_attempts():
    """After 3 ping_mark_pending calls without success, ping_was_sent returns True."""
    store = _fresh()
    store.ping_mark_pending("job", "r1", "ana")  # attempts=1
    assert store.ping_was_sent("job", "r1", "ana") is False
    store.ping_mark_failed("job", "r1", "ana", "err1")
    store.ping_mark_pending("job", "r1", "ana")  # attempts=2
    assert store.ping_was_sent("job", "r1", "ana") is False
    store.ping_mark_failed("job", "r1", "ana", "err2")
    store.ping_mark_pending("job", "r1", "ana")  # attempts=3
    assert store.ping_was_sent("job", "r1", "ana") is True  # dead-lettered


def test_migration_adds_columns_to_existing_table():
    """Simulate DB with old ping_log schema (no tri-state columns)."""
    store = SqliteStore(":memory:")
    # Build old schema manually (no attempts/failed_at/last_error)
    store._mem_conn.executescript("""
        CREATE TABLE ping_log (
            kind TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            sent_at TEXT,
            PRIMARY KEY (kind, ref_id, agent_name)
        );
        INSERT INTO ping_log (kind, ref_id, agent_name, sent_at) VALUES ('x', 'y', 'z', '2026-01-01');
        INSERT INTO ping_log (kind, ref_id, agent_name, sent_at) VALUES ('a', 'b', 'c', NULL);
    """)
    store._mem_conn.commit()
    store.init_db()
    cols = {r[1] for r in store.conn.execute("PRAGMA table_info(ping_log)").fetchall()}
    assert "attempts" in cols
    assert "failed_at" in cols
    assert "last_error" in cols
    # already-sent row backfilled to attempts=1
    sent_row = store.conn.execute("SELECT attempts FROM ping_log WHERE kind='x'").fetchone()
    assert sent_row["attempts"] == 1
    # pending row stays at attempts=0
    pending_row = store.conn.execute("SELECT attempts FROM ping_log WHERE kind='a'").fetchone()
    assert pending_row["attempts"] == 0
