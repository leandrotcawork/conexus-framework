# Memory & Wiki Phase 2 — GitHubAppBackend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add GitHubAppBackend so per-agent wikis sync to a GitHub repo using GitHub App installation tokens — no PATs, no SSH keys.

**Architecture:** JWT-signed GitHub App tokens mint short-lived installation tokens; git subprocess syncs a local clone (`agents/<name>/wiki/`) to `https://x-access-token:<token>@github.com/<owner>/<repo>.git`; Studio gains an OAuth install-callback route that stores `(agent_id, repo_slug, installation_id)` in a new `github_app_installs` table; Studio agent-detail page gains a Connect/Disconnect button.

**Tech Stack:** Python 3.12, httpx (existing), PyJWT (existing), git subprocess, FastAPI, SQLite, Jinja2

---

## File structure

**New files:**
- `src/conexus/core/memory/wiki/git_auth.py` — `_make_jwt()`, `get_installation_token()` with in-memory cache. ~50 lines.
- `src/conexus/core/memory/wiki/github_app.py` — `GitHubAppBackend` implementing WikiBackend protocol. ~120 lines.
- `src/conexus/web/admin/routes/github_wiki.py` — FastAPI router: `GET /admin/oauth/github/start` + `GET /admin/oauth/github/callback`. ~70 lines.
- `src/conexus/tests/core/memory/wiki/test_git_auth.py` — unit tests for JWT + token minting (mocked httpx).
- `src/conexus/tests/core/memory/wiki/test_github_app.py` — unit tests for GitHubAppBackend (mocked subprocess + LocalBackend).
- `src/conexus/tests/core/memory/test_github_app_store.py` — unit tests for SqliteStore helpers.
- `src/conexus/tests/web/test_github_wiki_route.py` — unit tests for OAuth callback route.

**Modified files:**
- `src/conexus/core/memory/sqlite_store.py` — add `github_app_installs` table to SCHEMA + 3 helper methods.
- `src/conexus/core/memory/wiki/__init__.py` — export `GitHubAppBackend`.
- `src/conexus/cli/identity_runtime.py` — update `_build_wiki()` signature + implement `github_app` case.
- `src/conexus/web/admin/app.py` — include `make_github_wiki_router()`.
- `src/conexus/web/admin/routes/agents.py` — add disconnect endpoint + pass `github_install` to template.
- `src/conexus/web/admin/templates/agents/edit.html` — add GitHub Wiki Connect/Disconnect section.

## Dispatch order

```
Parallel A:  Task 1 (git_auth)  +  Task 2 (DB schema)
             ↓                         ↓
Parallel B:  Task 3 (GitHubAppBackend) + Task 4 (OAuth callback route)
             (T3 needs T1; T4 needs T2 — start both after Parallel A)
             ↓                         ↓
             Task 5 (identity_runtime) Task 6 (Studio UI)
             (T5 needs T3)             (T6 needs T4)
                          ↓
                   Codex validate
```

---

## Task 1: JWT signing + token minting (`git_auth.py`)

**Files:**
- Create: `src/conexus/core/memory/wiki/git_auth.py`
- Create: `src/conexus/tests/core/memory/wiki/test_git_auth.py`

**Dependency check:** Verify `cryptography` is available (used in tests for RSA key generation):

- [ ] **Step 1: Check deps**

```bash
uv run python -c "from cryptography.hazmat.primitives.asymmetric import rsa; print('ok')"
```

If it prints `ok`, continue. If `ModuleNotFoundError`, add `cryptography` to `[dependency-groups] dev` in `pyproject.toml` then run `uv sync`.

- [ ] **Step 2: Create test file**

Create `src/conexus/tests/core/memory/wiki/test_git_auth.py`:

```python
"""Tests for GitHub App JWT signing and token minting."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _generate_pem() -> tuple[str, object]:
    """Return (pem_str, public_key) for a fresh RSA key."""
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return pem, key.public_key()


def test_make_jwt_encodes_app_id():
    from conexus.core.memory.wiki.git_auth import _make_jwt

    pem, pub = _generate_pem()
    token = _make_jwt("123", pem)
    payload = jwt.decode(token, pub, algorithms=["RS256"])
    assert payload["iss"] == "123"


def test_make_jwt_expiry_window():
    import time
    from conexus.core.memory.wiki.git_auth import _make_jwt

    pem, pub = _generate_pem()
    before = int(time.time())
    token = _make_jwt("app1", pem)
    payload = jwt.decode(token, pub, algorithms=["RS256"])
    assert payload["iat"] <= before
    assert payload["exp"] > before
    assert payload["exp"] - payload["iat"] <= 600  # <=10 min per GitHub limit


def test_get_installation_token_calls_github():
    from conexus.core.memory.wiki.git_auth import _TOKEN_CACHE, get_installation_token

    _TOKEN_CACHE.clear()
    pem, _ = _generate_pem()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"token": "ghs_abc", "expires_at": "2099-01-01T00:00:00Z"}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        token = get_installation_token("app123", pem, 42)

    assert token == "ghs_abc"
    mock_post.assert_called_once()
    assert "42" in mock_post.call_args[0][0]


def test_token_cached_on_second_call():
    from conexus.core.memory.wiki.git_auth import _TOKEN_CACHE, get_installation_token

    _TOKEN_CACHE.clear()
    pem, _ = _generate_pem()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"token": "ghs_xyz", "expires_at": "2099-01-01T00:00:00Z"}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        get_installation_token("app", pem, 99)
        get_installation_token("app", pem, 99)

    assert mock_post.call_count == 1  # second call uses cache
```

- [ ] **Step 3: Run test — expect FAIL (import error)**

```bash
uv run pytest src/conexus/tests/core/memory/wiki/test_git_auth.py -v
```

Expected: `ImportError: cannot import name '_make_jwt'`

- [ ] **Step 4: Create implementation**

Create `src/conexus/core/memory/wiki/git_auth.py`:

```python
"""GitHub App JWT signing and installation-token minting."""
from __future__ import annotations

import time
from datetime import datetime

import httpx
import jwt

# module-level cache: installation_id -> (token, expires_epoch)
_TOKEN_CACHE: dict[int, tuple[str, float]] = {}


def _make_jwt(app_id: str, private_key_pem: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": app_id},
        private_key_pem,
        algorithm="RS256",
    )


def get_installation_token(app_id: str, private_key_pem: str, installation_id: int) -> str:
    """Return a valid GitHub App installation token (cached until 5 min before expiry)."""
    token, expires = _TOKEN_CACHE.get(installation_id, ("", 0.0))
    if token and time.time() < expires - 300:
        return token
    app_jwt = _make_jwt(app_id, private_key_pem)
    resp = httpx.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
    _TOKEN_CACHE[installation_id] = (data["token"], expires_at)
    return data["token"]
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
uv run pytest src/conexus/tests/core/memory/wiki/test_git_auth.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/conexus/core/memory/wiki/git_auth.py src/conexus/tests/core/memory/wiki/test_git_auth.py
git commit -m "feat: github app jwt signing + installation token minting"
```

---

## Task 2: `github_app_installs` DB table + SqliteStore helpers

**Files:**
- Modify: `src/conexus/core/memory/sqlite_store.py`
- Create: `src/conexus/tests/core/memory/test_github_app_store.py`

- [ ] **Step 1: Create test file**

Create `src/conexus/tests/core/memory/test_github_app_store.py`:

```python
"""Tests for github_app_installs table + SqliteStore helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    s = SqliteStore(str(tmp_path / "test.db"))
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
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest src/conexus/tests/core/memory/test_github_app_store.py -v
```

Expected: `AttributeError: 'SqliteStore' object has no attribute 'github_app_install_set'`

- [ ] **Step 3: Add table to SCHEMA in sqlite_store.py**

In `src/conexus/core/memory/sqlite_store.py`, find the line `CREATE TABLE IF NOT EXISTS pack_migrations` and insert the new table definition **before** it (after the `oauth_clients` table closing semicolon):

```python
CREATE TABLE IF NOT EXISTS github_app_installs (
    agent_id        TEXT PRIMARY KEY,
    repo_slug       TEXT NOT NULL,
    installation_id INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);
```

The SCHEMA string currently ends the `oauth_clients` block with `);` then has `pack_migrations`. Insert the new block between them.

- [ ] **Step 4: Add 3 methods to SqliteStore class**

In `src/conexus/core/memory/sqlite_store.py`, find the end of the class and append after the last existing method (before any module-level code below the class):

```python
# ----- github app installs -----

def github_app_install_set(
    self, agent_id: str, repo_slug: str, installation_id: int
) -> None:
    with self.connect() as conn:
        conn.execute(
            """INSERT INTO github_app_installs (agent_id, repo_slug, installation_id, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(agent_id) DO UPDATE SET
                 repo_slug=excluded.repo_slug,
                 installation_id=excluded.installation_id,
                 created_at=excluded.created_at""",
            (agent_id, repo_slug, installation_id, _now_iso()),
        )
        conn.commit()

def github_app_install_get(self, agent_id: str) -> dict | None:
    with self.connect() as conn:
        row = conn.execute(
            "SELECT agent_id, repo_slug, installation_id, created_at"
            " FROM github_app_installs WHERE agent_id=?",
            (agent_id,),
        ).fetchone()
    return dict(row) if row else None

def github_app_install_delete(self, agent_id: str) -> None:
    with self.connect() as conn:
        conn.execute(
            "DELETE FROM github_app_installs WHERE agent_id=?", (agent_id,)
        )
        conn.commit()
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
uv run pytest src/conexus/tests/core/memory/test_github_app_store.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/conexus/core/memory/sqlite_store.py src/conexus/tests/core/memory/test_github_app_store.py
git commit -m "feat: github_app_installs table + SqliteStore helpers"
```

---

## Task 3: GitHubAppBackend

**Prerequisite:** Task 1 complete.

**Files:**
- Create: `src/conexus/core/memory/wiki/github_app.py`
- Create: `src/conexus/tests/core/memory/wiki/test_github_app.py`
- Modify: `src/conexus/core/memory/wiki/__init__.py`

- [ ] **Step 1: Create test file**

Create `src/conexus/tests/core/memory/wiki/test_github_app.py`:

```python
"""Tests for GitHubAppBackend (subprocess + LocalBackend mocked)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_FAKE_PEM = "fake-pem"
_FAKE_APP_ID = "app1"
_FAKE_INSTALL_ID = 42
_FAKE_REPO = "owner/repo"


def _subprocess_ok() -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = ""
    m.stderr = ""
    return m


def _make_backend(tmp_path: Path):
    from conexus.core.memory.wiki.github_app import GitHubAppBackend

    with patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        return GitHubAppBackend(
            local_root=tmp_path,
            repo_slug=_FAKE_REPO,
            installation_id=_FAKE_INSTALL_ID,
            app_id=_FAKE_APP_ID,
            private_key_pem=_FAKE_PEM,
        )


def test_write_then_read(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    with patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        b.write("note.md", "hello")
        content = b.read("note.md")
    assert content == "hello"


def test_list_delegates_to_local(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    with patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        b.write("a.md", "x")
        b.write("b.md", "y")
        result = b.list()
    assert sorted(result) == ["a.md", "b.md"]


def test_search_delegates_to_local(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    with patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        b.write("x.md", "the brown fox")
        hits = b.search("brown")
    assert len(hits) == 1
    assert "brown" in hits[0]["snippet"]


def test_delete(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    with patch("conexus.core.memory.wiki.github_app.get_installation_token", return_value="ghs_tok"), \
         patch("subprocess.run", return_value=_subprocess_ok()):
        b.write("del.md", "bye")
        b.delete("del.md")
    assert not b.exists("del.md")


def test_exists_no_network(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    assert not b.exists("ghost.md")


def test_delete_missing_raises(tmp_path: Path) -> None:
    b = _make_backend(tmp_path)
    with pytest.raises(FileNotFoundError):
        b.delete("nope.md")
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest src/conexus/tests/core/memory/wiki/test_github_app.py -v
```

Expected: `ImportError: cannot import name 'GitHubAppBackend'`

- [ ] **Step 3: Create implementation**

Create `src/conexus/core/memory/wiki/github_app.py`:

```python
"""GitHub App wiki backend — per-agent repo, git-backed."""
from __future__ import annotations

import subprocess
from pathlib import Path

from conexus.core.memory.wiki.git_auth import get_installation_token
from conexus.core.memory.wiki.local import LocalBackend


class GitHubAppBackend:
    """Sync WikiBackend backed by a GitHub repo via App installation tokens.

    Tech debt: git subprocess calls block the event loop.
    Acceptable for single-user MVP; wrap in asyncio.to_thread when needed.
    """

    def __init__(
        self,
        *,
        local_root: Path,
        repo_slug: str,
        installation_id: int,
        app_id: str,
        private_key_pem: str,
    ) -> None:
        self._root = Path(local_root).resolve()
        self._repo_slug = repo_slug
        self._installation_id = installation_id
        self._app_id = app_id
        self._private_key = private_key_pem
        self._local = LocalBackend(local_root)
        self._ensure_clone()

    # --- internal helpers ---

    def _token(self) -> str:
        return get_installation_token(self._app_id, self._private_key, self._installation_id)

    def _remote_url(self) -> str:
        return f"https://x-access-token:{self._token()}@github.com/{self._repo_slug}.git"

    def _git(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self._root, capture_output=True, text=True
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git {args[0]!r} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def _ensure_clone(self) -> None:
        if (self._root / ".git").exists():
            return
        self._root.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", self._remote_url(), "."],
            cwd=self._root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Empty repo — init locally then add remote
            subprocess.run(["git", "init"], cwd=self._root, check=True, capture_output=True)
            subprocess.run(
                ["git", "remote", "add", "origin", self._remote_url()],
                cwd=self._root,
                check=True,
                capture_output=True,
            )
        self._git("config", "user.name", "Conexus")
        self._git("config", "user.email", "noreply@conexus.ai")
        # Seed initial commit if repo has no history
        if not self._git("log", "--oneline", "-1", check=False):
            (self._root / "README.md").write_text(
                f"# {self._repo_slug.split('/')[-1]}\n\nWiki for Conexus agent.\n"
            )
            self._git("add", "-A")
            self._git("commit", "-m", "chore: initial commit")
            self._git("push", "origin", "HEAD:main")

    def _refresh_remote(self) -> None:
        self._git("remote", "set-url", "origin", self._remote_url())

    def _pull(self) -> None:
        self._refresh_remote()
        self._git("pull", "--ff-only", "origin", "main", check=False)

    def _commit_push(self, message: str) -> None:
        self._git("add", "-A")
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=self._root, capture_output=True
        )
        if diff.returncode == 0:
            return  # nothing staged
        self._git("commit", "-m", message)
        self._refresh_remote()
        self._git("push", "origin", "main")

    # --- WikiBackend interface ---

    def read(self, path: str) -> str:
        self._pull()
        return self._local.read(path)

    def write(self, path: str, content: str) -> None:
        self._pull()
        self._local.write(path, content)
        self._commit_push(f"chore: update {path}")

    def list(self, folder: str = "") -> list[str]:
        self._pull()
        return self._local.list(folder)

    def search(self, query: str) -> list[dict]:
        self._pull()
        return self._local.search(query)

    def exists(self, path: str) -> bool:
        return self._local.exists(path)

    def delete(self, path: str) -> None:
        self._pull()
        self._local.delete(path)
        self._commit_push(f"chore: delete {path}")
```

- [ ] **Step 4: Update `__init__.py`**

Replace the contents of `src/conexus/core/memory/wiki/__init__.py`:

```python
"""Wiki backend package."""
from conexus.core.memory.wiki.backend import WikiBackend, safe_join
from conexus.core.memory.wiki.github_app import GitHubAppBackend
from conexus.core.memory.wiki.local import LocalBackend

__all__ = ["WikiBackend", "GitHubAppBackend", "LocalBackend", "safe_join"]
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
uv run pytest src/conexus/tests/core/memory/wiki/test_github_app.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/conexus/core/memory/wiki/github_app.py src/conexus/core/memory/wiki/__init__.py src/conexus/tests/core/memory/wiki/test_github_app.py
git commit -m "feat: GitHubAppBackend (git subprocess, local clone)"
```

---

## Task 4: OAuth install callback route

**Prerequisite:** Task 2 complete.

**Files:**
- Create: `src/conexus/web/admin/routes/github_wiki.py`
- Create: `src/conexus/tests/web/test_github_wiki_route.py`
- Modify: `src/conexus/web/admin/app.py`

**Flow:**
1. `GET /admin/oauth/github/start?agent=<name>&repo=<owner/repo>` — store `"gh:agent:repo"` in `oauth_pkce_state.code_verifier`, redirect to GitHub App install URL.
2. `GET /admin/oauth/github/callback?installation_id=<N>&state=<nonce>` — verify nonce, retrieve agent+repo from `code_verifier`, write to `github_app_installs`, redirect to agent detail page.

Env vars used: `GITHUB_APP_SLUG` (e.g. `"conexus-ai"`), `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`.

- [ ] **Step 1: Create test file**

Create `src/conexus/tests/web/test_github_wiki_route.py`:

```python
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
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest src/conexus/tests/web/test_github_wiki_route.py -v
```

Expected: `ImportError: cannot import name 'make_github_wiki_router'`

- [ ] **Step 3: Create route file**

Create `src/conexus/web/admin/routes/github_wiki.py`:

```python
"""GitHub App OAuth install callback for wiki backend."""
from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from conexus.core.memory.sqlite_store import SqliteStore


def make_github_wiki_router(store: SqliteStore) -> APIRouter:
    router = APIRouter(prefix="/admin/oauth/github")

    @router.get("/start")
    async def start(
        agent: str = Query(...),
        repo: str = Query(...),
    ) -> RedirectResponse:
        app_slug = os.environ["GITHUB_APP_SLUG"]
        nonce = secrets.token_urlsafe(16)
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO oauth_pkce_state (nonce, code_verifier, created_at)"
                " VALUES (?, ?, datetime('now'))",
                (nonce, f"gh:{agent}:{repo}"),  # prefix isolates from Phase 11 PKCE rows
            )
            conn.commit()
        gh_url = f"https://github.com/apps/{app_slug}/installations/new?state={nonce}"
        return RedirectResponse(gh_url)

    @router.get("/callback")
    async def callback(
        installation_id: int = Query(...),
        state: str = Query(...),
    ) -> RedirectResponse:
        with store.connect() as conn:
            row = conn.execute(
                "SELECT code_verifier FROM oauth_pkce_state WHERE nonce=?", (state,)
            ).fetchone()
            if not row:
                raise HTTPException(400, "invalid state")
            payload = row["code_verifier"]
            if not payload.startswith("gh:"):
                raise HTTPException(400, "invalid state")
            _, agent, repo_slug = payload.split(":", 2)
            conn.execute("DELETE FROM oauth_pkce_state WHERE nonce=?", (state,))
            conn.commit()
        store.github_app_install_set(agent, repo_slug, installation_id)
        return RedirectResponse(f"/admin/agents/{agent}")

    return router
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest src/conexus/tests/web/test_github_wiki_route.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Include router in app.py**

In `src/conexus/web/admin/app.py`, add the import at the top with the other route imports:

```python
from .routes.github_wiki import make_github_wiki_router
```

And in `make_admin_app`, after the existing `include_router` calls, add:

```python
from conexus.core.memory.sqlite_store import SqliteStore as _SqliteStore
_store = _SqliteStore(str(data_dir / "conexus.db"))
_store.init_db()
app.include_router(make_github_wiki_router(_store))
```

- [ ] **Step 6: Smoke-check app builds**

```bash
uv run python -c "
from pathlib import Path
from conexus.web.admin.app import make_admin_app
app = make_admin_app(agents_dir=Path('/tmp'), data_dir=Path('/tmp'))
print('ok')
"
```

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add src/conexus/web/admin/routes/github_wiki.py src/conexus/tests/web/test_github_wiki_route.py src/conexus/web/admin/app.py
git commit -m "feat: github wiki oauth install callback route"
```

---

## Task 5: Wire GitHubAppBackend into identity_runtime

**Prerequisite:** Task 3 complete.

**Files:**
- Modify: `src/conexus/cli/identity_runtime.py`
- Modify: `src/conexus/tests/cli/test_identity_runtime_backends.py`

- [ ] **Step 1: Update test file**

In `src/conexus/tests/cli/test_identity_runtime_backends.py`, replace `test_github_app_backend_raises_not_implemented` with two new tests:

```python
def test_github_app_backend_builds_from_store(tmp_path):
    """When store has install row and env vars are set, backend builds successfully."""
    from unittest.mock import patch

    from conexus.cli.identity_runtime import _build_wiki
    from conexus.core.config.skill_loader import WikiSection
    from conexus.core.memory.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "test.db"))
    store.init_db()
    store.github_app_install_set("myagent", "owner/repo", 99)

    wiki_cfg = WikiSection(backend="github_app", repo="owner/repo")

    with patch("conexus.core.memory.wiki.github_app.GitHubAppBackend._ensure_clone"), \
         patch.dict("os.environ", {"GITHUB_APP_ID": "123", "GITHUB_APP_PRIVATE_KEY": "pem"}):
        ws = _build_wiki(wiki_cfg, tmp_path, agent_id="myagent", store=store)

    assert ws is not None


def test_github_app_backend_missing_install_raises(tmp_path):
    import pytest

    from conexus.cli.identity_runtime import _build_wiki
    from conexus.core.config.skill_loader import WikiSection
    from conexus.core.memory.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "test.db"))
    store.init_db()
    wiki_cfg = WikiSection(backend="github_app", repo="owner/repo")

    with pytest.raises(RuntimeError, match="not connected"):
        _build_wiki(wiki_cfg, tmp_path, agent_id="myagent", store=store)
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest src/conexus/tests/cli/test_identity_runtime_backends.py -v
```

Expected: `TypeError` (wrong signature for `_build_wiki`) or `NotImplementedError`.

- [ ] **Step 3: Update identity_runtime.py**

Replace `_build_wiki` and update its call site in `IdentityRuntime.__init__` in `src/conexus/cli/identity_runtime.py`:

```python
def _build_wiki(
    wiki_cfg: WikiSection,
    skill_dir: Path,
    *,
    agent_id: str = "",
    store: SqliteStore | None = None,
) -> WikiStore:
    if wiki_cfg.backend == "local":
        wiki_path = (
            skill_dir / wiki_cfg.dir
            if not Path(wiki_cfg.dir).is_absolute()
            else Path(wiki_cfg.dir)
        )
        return WikiStore.local(wiki_path)
    if wiki_cfg.backend == "github_app":
        if store is None:
            raise RuntimeError("store required for github_app wiki backend")
        row = store.github_app_install_get(agent_id)
        if row is None:
            raise RuntimeError(
                f"Agent '{agent_id}' github wiki not connected. "
                "Go to Studio → agent → Connect GitHub Wiki first."
            )
        import os
        from conexus.core.memory.wiki.github_app import GitHubAppBackend
        backend = GitHubAppBackend(
            local_root=skill_dir / "wiki",
            repo_slug=row["repo_slug"],
            installation_id=row["installation_id"],
            app_id=os.environ["GITHUB_APP_ID"],
            private_key_pem=os.environ["GITHUB_APP_PRIVATE_KEY"],
        )
        return WikiStore(backend)
    raise ValueError(f"unknown wiki backend: {wiki_cfg.backend!r}")
```

Also update the call site in `IdentityRuntime.__init__` (line `self.wiki = _build_wiki(cfg.wiki, skill_dir)`):

```python
if cfg.wiki:
    self.wiki = _build_wiki(cfg.wiki, skill_dir, agent_id=agent_id, store=store)
```

- [ ] **Step 4: Run all identity_runtime tests — expect PASS**

```bash
uv run pytest src/conexus/tests/cli/test_identity_runtime_backends.py -v
```

Expected: 4 passed (`test_local_backend_creates_wikistore`, `test_github_app_backend_builds_from_store`, `test_github_app_backend_missing_install_raises`, `test_no_wiki_block_yields_no_wiki`).

- [ ] **Step 5: Commit**

```bash
git add src/conexus/cli/identity_runtime.py src/conexus/tests/cli/test_identity_runtime_backends.py
git commit -m "feat: wire GitHubAppBackend in identity_runtime"
```

---

## Task 6: Studio UI — Connect / Disconnect GitHub Wiki

**Prerequisite:** Task 4 complete.

**Files:**
- Modify: `src/conexus/web/admin/routes/agents.py`
- Modify: `src/conexus/web/admin/templates/agents/edit.html`

- [ ] **Step 1: Add disconnect endpoint + github_install context to detail_view**

In `src/conexus/web/admin/routes/agents.py`, add the import at the top:

```python
from conexus.core.memory.sqlite_store import SqliteStore
```

Update `detail_view` to fetch the install row. The current `detail_view` ends by calling `TemplateResponse`. Add after `agent = read_agent(ctx.agents_dir, name)`:

```python
_store = SqliteStore(str(ctx.data_dir / "conexus.db"))
_store.init_db()
github_install = _store.github_app_install_get(name)
```

And pass it in the template context dict:

```python
"github_install": github_install,
```

Then add a disconnect endpoint inside `make_agents_router()` (after `save`):

```python
@router.post("/agents/{name}/github-wiki/disconnect")
async def github_wiki_disconnect(request: Request, name: str) -> RedirectResponse:
    ctx = request.app.state.ctx
    store = SqliteStore(str(ctx.data_dir / "conexus.db"))
    store.init_db()
    store.github_app_install_delete(name)
    return RedirectResponse(f"/admin/agents/{name}", status_code=303)
```

- [ ] **Step 2: Verify the route is importable**

```bash
uv run python -c "
from conexus.web.admin.routes.agents import make_agents_router
r = make_agents_router()
routes = [str(r.path) for r in r.routes]
print([r for r in routes if 'github' in r])
"
```

Expected: `['/admin/agents/{name}/github-wiki/disconnect']`

- [ ] **Step 3: Add GitHub Wiki section to edit.html template**

In `src/conexus/web/admin/templates/agents/edit.html`, insert the following **after the REPL panel `</div>` closing tag** (after the closing `</div>` of the `card p-4 mt-4` REPL block, before `</section>`):

```html
{% if agent.skill.frontmatter.identity and agent.skill.frontmatter.identity.wiki and agent.skill.frontmatter.identity.wiki.backend == "github_app" %}
<div class="card p-4 mt-4">
  <h3 class="text-sm font-semibold text-slate-700 mb-3">GitHub Wiki</h3>
  {% if github_install %}
    <p class="text-sm text-slate-600 mb-3">
      Connected: <code class="font-mono text-xs bg-slate-100 px-1 rounded">{{ github_install.repo_slug }}</code>
    </p>
    <form method="post" action="/admin/agents/{{ agent.name }}/github-wiki/disconnect">
      <button type="submit" class="text-xs text-red-600 hover:text-red-800 transition-colors">
        Disconnect
      </button>
    </form>
  {% else %}
    <p class="text-sm text-slate-500 mb-2">
      Create <code class="font-mono text-xs bg-slate-100 px-1 rounded">owner/{{ agent.name }}-wiki</code>
      on GitHub first, then connect:
    </p>
    <form method="get" action="/admin/oauth/github/start" class="flex gap-2 items-center">
      <input type="hidden" name="agent" value="{{ agent.name }}">
      <input type="text" name="repo" placeholder="owner/{{ agent.name }}-wiki"
             class="input text-sm flex-1" required>
      <button type="submit" class="btn-primary text-sm px-3">Connect</button>
    </form>
  {% endif %}
</div>
{% endif %}
```

Note: `agent.skill.frontmatter` is `fm` in the template context — the template already has `fm` available. Use `fm` instead:

```html
{% if fm.identity and fm.identity.wiki and fm.identity.wiki.backend == "github_app" %}
```

- [ ] **Step 4: Verify template renders**

Run the Studio and navigate to an agent that has `wiki.backend: github_app` in its SKILL.md. Confirm the Connect section renders. If no such agent exists locally, temporarily add to any agent's SKILL.md:

```yaml
identity:
  enabled: true
  wiki:
    backend: github_app
    repo: owner/test-wiki
```

Then check the detail page. The section should appear with the repo input form.

- [ ] **Step 5: Commit**

```bash
git add src/conexus/web/admin/routes/agents.py src/conexus/web/admin/templates/agents/edit.html
git commit -m "feat: studio UI connect/disconnect github wiki"
```

---

## Codex validation

Run after all tasks complete.

- [ ] **Step 1: Full test suite for new code**

```bash
uv run pytest src/conexus/tests/core/memory/wiki/test_git_auth.py src/conexus/tests/core/memory/wiki/test_github_app.py src/conexus/tests/core/memory/test_github_app_store.py src/conexus/tests/cli/test_identity_runtime_backends.py src/conexus/tests/web/test_github_wiki_route.py -v
```

Expected: all pass.

- [ ] **Step 2: Lint**

```bash
uv run ruff check src/conexus/core/memory/wiki/git_auth.py src/conexus/core/memory/wiki/github_app.py src/conexus/web/admin/routes/github_wiki.py src/conexus/cli/identity_runtime.py src/conexus/core/memory/sqlite_store.py
```

Fix any issues, then commit: `git commit -m "fix: ruff lint issues"`

- [ ] **Step 3: Full test suite**

```bash
uv run pytest
```

Confirm no regressions.
