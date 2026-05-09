"""Tests for GitHub Wiki OAuth install callback routes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.web.admin.routes.github_wiki import make_github_wiki_router


def _make_app(store: SqliteStore, tmp_path: Path) -> FastAPI:
    @dataclass
    class Ctx:
        data_dir: Path = tmp_path
        agents_dir: Path = tmp_path / "agents"

    app = FastAPI()
    app.state.ctx = Ctx()
    app.include_router(make_github_wiki_router(store))
    return app


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    s = SqliteStore(str(tmp_path / "test.db"))
    s.init_db()
    return s


@pytest.fixture
def client(store: SqliteStore, tmp_path: Path) -> TestClient:
    return TestClient(_make_app(store, tmp_path), follow_redirects=False)


def test_start_redirects_to_github(client: TestClient) -> None:
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"GITHUB_APP_SLUG": "test-app"}):
        resp = client.get("/admin/oauth/github/start?agent=validator&repo=owner/validator-wiki")

    assert resp.status_code in (302, 307)
    assert "github.com/apps/test-app/installations/new" in resp.headers["location"]


def test_start_stores_nonce(store: SqliteStore, tmp_path: Path) -> None:
    import os
    from unittest.mock import patch

    client = TestClient(_make_app(store, tmp_path), follow_redirects=False)
    with patch.dict(os.environ, {"GITHUB_APP_SLUG": "test-app"}):
        client.get("/admin/oauth/github/start?agent=myagent&repo=owner/myagent-wiki")

    with store.connect() as conn:
        rows = conn.execute("SELECT code_verifier FROM oauth_pkce_state").fetchall()
    assert len(rows) == 1
    assert rows[0]["code_verifier"] == "gh:myagent:owner/myagent-wiki"


def test_callback_writes_install(store: SqliteStore, tmp_path: Path) -> None:
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO oauth_pkce_state (nonce, code_verifier, created_at)"
            " VALUES ('abc123', 'gh:validator:owner/validator-wiki', '2026-01-01')"
        )
        conn.commit()

    client = TestClient(_make_app(store, tmp_path), follow_redirects=False)
    resp = client.get("/admin/oauth/github/callback?installation_id=99&state=abc123")

    assert resp.status_code in (302, 307)
    assert "/admin/agents/validator" in resp.headers["location"]
    row = store.github_app_install_get("validator")
    assert row is not None
    assert row["installation_id"] == 99
    assert row["repo_slug"] == "owner/validator-wiki"


def test_callback_consumes_nonce(store: SqliteStore, tmp_path: Path) -> None:
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO oauth_pkce_state (nonce, code_verifier, created_at)"
            " VALUES ('xyz', 'gh:agent1:owner/repo', '2026-01-01')"
        )
        conn.commit()

    client = TestClient(_make_app(store, tmp_path), follow_redirects=False)
    client.get("/admin/oauth/github/callback?installation_id=1&state=xyz")

    with store.connect() as conn:
        row = conn.execute("SELECT * FROM oauth_pkce_state WHERE nonce='xyz'").fetchone()
    assert row is None  # consumed


def test_callback_bad_state_returns_400(store: SqliteStore, tmp_path: Path) -> None:
    client = TestClient(_make_app(store, tmp_path), follow_redirects=False)
    resp = client.get("/admin/oauth/github/callback?installation_id=99&state=INVALID")
    assert resp.status_code == 400
