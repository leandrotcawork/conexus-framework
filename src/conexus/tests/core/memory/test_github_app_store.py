"""Tests for github_app_installs table + SqliteStore helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    s = SqliteStore(":memory:")
    s.init_db()
    return s


def test_set_and_get(store: SqliteStore) -> None:
    store.github_app_install_set("agent1", "owner/repo", 42)
    row = store.github_app_install_get("agent1")
    assert row is not None
    assert row["repo_slug"] == "owner/repo"
    assert row["installation_id"] == 42


def test_get_missing_returns_none(store: SqliteStore) -> None:
    assert store.github_app_install_get("nobody") is None


def test_set_overwrites(store: SqliteStore) -> None:
    store.github_app_install_set("agent1", "owner/repo1", 1)
    store.github_app_install_set("agent1", "owner/repo2", 2)
    row = store.github_app_install_get("agent1")
    assert row is not None
    assert row["repo_slug"] == "owner/repo2"
    assert row["installation_id"] == 2


def test_delete(store: SqliteStore) -> None:
    store.github_app_install_set("agent1", "owner/repo", 1)
    store.github_app_install_delete("agent1")
    assert store.github_app_install_get("agent1") is None


def test_delete_missing_is_noop(store: SqliteStore) -> None:
    store.github_app_install_delete("nobody")  # must not raise
