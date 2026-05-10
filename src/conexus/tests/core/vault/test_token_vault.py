import time

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.vault.token_vault import TokenVault


def test_put_get_round_trip(tmp_path):
    store = SqliteStore(":memory:")
    store.init_db()
    v = TokenVault(store, master_secret=b"x" * 32)
    v.put(
        "u1",
        "https://mcp.example/",
        access_token="at1",
        refresh_token="rt1",
        expires_at=int(time.time()) + 3600,
        scopes=["calendar.read"],
    )
    rec = v.get("u1", "https://mcp.example/")
    assert rec.access_token == "at1"
    assert rec.refresh_token == "rt1"
    assert "calendar.read" in rec.scopes


def test_get_missing_returns_none(tmp_path):
    store = SqliteStore(":memory:")
    store.init_db()
    v = TokenVault(store, master_secret=b"x" * 32)
    assert v.get("u1", "https://mcp.example/") is None


def test_expired_flag(tmp_path):
    store = SqliteStore(":memory:")
    store.init_db()
    v = TokenVault(store, master_secret=b"x" * 32)
    v.put(
        "u1",
        "https://mcp.example/",
        access_token="at",
        refresh_token=None,
        expires_at=int(time.time()) - 10,
        scopes=[],
    )
    rec = v.get("u1", "https://mcp.example/")
    assert rec.is_expired


def test_delete(tmp_path):
    store = SqliteStore(":memory:")
    store.init_db()
    v = TokenVault(store, master_secret=b"x" * 32)
    v.put(
        "u1",
        "https://mcp.example/",
        access_token="at",
        refresh_token=None,
        expires_at=int(time.time()) + 60,
        scopes=[],
    )
    v.delete("u1", "https://mcp.example/")
    assert v.get("u1", "https://mcp.example/") is None
