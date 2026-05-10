from pathlib import Path
from conexus.core.memory.sqlite_store import SqliteStore


def test_apply_migrations_creates_table(tmp_path: Path):
    store = SqliteStore(":memory:")
    store.init_db()
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "001_init.sql").write_text(
        "CREATE TABLE pack_demo_x (id INTEGER PRIMARY KEY, val TEXT);"
    )
    store.apply_pack_migrations("demo", sql_dir)
    with store.connect() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pack_demo_x'").fetchall()
    assert len(rows) == 1


def test_apply_migrations_idempotent(tmp_path: Path):
    store = SqliteStore(":memory:")
    store.init_db()
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "001_init.sql").write_text(
        "CREATE TABLE pack_demo_x (id INTEGER PRIMARY KEY);"
    )
    store.apply_pack_migrations("demo", sql_dir)
    store.apply_pack_migrations("demo", sql_dir)  # second call must not raise
    with store.connect() as conn:
        rows = conn.execute("SELECT version FROM pack_migrations WHERE pack_id=?", ("demo",)).fetchall()
    assert len(rows) == 1
