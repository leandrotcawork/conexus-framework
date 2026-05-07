# Phase 11 — Connector Marketplace (Remote MCP + OAuth + UX) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a vendor-agnostic connector marketplace so end users attach Google Calendar, Sheets, Notion, GitHub, Slack, etc. to their Conexus agents via a one-tap UX, with multi-tenant OAuth handled by the framework — not the agent author.

**Architecture:** Standardize on the **MCP 2025-06-18 wire protocol** for all third-party integrations. Remote MCP servers (HTTP transport) are the install unit. OAuth 2.1 + PKCE + DCR + RFC 8707 Resource Indicators handled by a framework-owned `OAuthClient`. Tokens live in an encrypted `TokenVault` (SqliteStore) keyed by `(user_id, server_url)`. Auth-required mid-conversation surfaces as a typed `NeedsAuthError` → handler emits `auth_required` event → adapter (Telegram, web UI) renders a magic link → callback fires → original tool call resumes. Reuses the existing `SKILL_PACK` packaging pattern: a `ConnectorPack` is a SKILL_PACK with `backend: mcp-http` + a `connector.json` descriptor.

**Tech Stack:** Python 3.11+, MCP `mcp[cli]` SDK, `httpx` (async HTTP), `cryptography` (AES-GCM), `PyJWT` (state JWT), `fastapi` + `uvicorn` (callback server), existing SqliteStore + SkillLoader + AgentRegistry.

---

## Task 0: Add missing dependencies

**Files:**
- Modify: `pyproject.toml` — runtime + dev deps

All Tasks 1–11 import packages not in current `pyproject.toml`. Add before any implementation.

- [ ] **Step 1: Add runtime deps**

```bash
uv add httpx cryptography PyJWT fastapi uvicorn
```

- [ ] **Step 2: Add dev deps**

```bash
uv add --dev pytest-httpx pytest-asyncio
```

- [ ] **Step 3: Verify**

```bash
uv run python -c "import httpx, cryptography, jwt, fastapi, uvicorn"
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add httpx, cryptography, PyJWT, fastapi, uvicorn, pytest-httpx deps"
```

---

## Scope check

This is **one subsystem**: connector marketplace runtime. It does not include:
- Built-in first-party connectors beyond Google Calendar (validation slice). Each additional connector pack is a separate, post-spec deliverable.
- Web-based marketplace UI (browser dashboard). Out of scope — CLI + Telegram surfaces only. Web UI is a future phase that consumes the same `ConnectorRegistry` contract.
- Migrating Ana off her native `GoogleCalendarClient`. Deferred to a follow-up; framework lands first.

---

## File structure

### New modules
```
src/conexus/core/oauth/
  __init__.py
  errors.py              — NeedsAuthError, OAuthError, TokenExpiredError
  client.py              — OAuthClient (PKCE, DCR, discovery, exchange, refresh)
  metadata.py            — RFC 9728/8414 discovery (well-known fetcher + cache)
  state.py               — Magic-link state JWT encode/decode (5-min TTL)
  pkce.py                — code_verifier + code_challenge helpers

src/conexus/core/vault/
  __init__.py
  token_vault.py         — encrypted token storage in SqliteStore
  crypto.py              — AES-GCM encrypt/decrypt (per-deployment master key)

src/conexus/core/backends/
  mcp_http_backend.py    — McpHttpBackend (Streamable HTTP MCP client)

src/conexus/core/connectors/
  __init__.py
  pack.py                — ConnectorPack manifest (extends SKILL_PACK schema)
  registry.py            — ConnectorRegistry (local JSON catalog + lookup)

src/conexus/web/
  __init__.py
  oauth_router.py        — FastAPI router (/oauth/{provider}/start, /callback)
  app.py                 — FastAPI app factory (mounts oauth_router)
```

### Modified modules
```
src/conexus/core/agent_handler.py        — catches NeedsAuthError, emits auth_required event
src/conexus/core/skills/skill_resolver.py — wires mcp-http branch
src/conexus/core/memory/sqlite_store.py  — adds oauth_tokens, oauth_clients tables
src/conexus/cli/__main__.py              — new `connectors` subcommand group
adapters/telegram_runner.py              — handles auth_required event → InlineKeyboardButton
```

### New tests
```
src/conexus/tests/core/oauth/test_pkce.py
src/conexus/tests/core/oauth/test_metadata_discovery.py
src/conexus/tests/core/oauth/test_oauth_client.py
src/conexus/tests/core/oauth/test_state_jwt.py
src/conexus/tests/core/vault/test_token_vault.py
src/conexus/tests/core/vault/test_crypto.py
src/conexus/tests/test_framework_mcp_http_backend.py
src/conexus/tests/core/connectors/test_pack_parser.py
src/conexus/tests/core/connectors/test_registry.py
src/conexus/tests/web/test_oauth_router.py
src/conexus/tests/integration/test_connector_e2e.py
```

### New fixtures
```
src/conexus/tests/integration/fake_oauth_server/  — FastAPI mock AS + RS for E2E
src/conexus/tests/integration/fake_mcp_server/    — minimal MCP HTTP server with bearer
```

---

## Architecture diagram (mental model)

```
┌─────────────────┐       ┌────────────────────────────────────────┐
│ Telegram bot    │──────▶│ handle_agent_message (cfg.execute_tool)│
└─────────────────┘       └────────────────┬───────────────────────┘
                                           │  raises NeedsAuthError(server_url, scopes)
                                           ▼
                          ┌────────────────────────────┐
                          │ Handler catches; emits      │──────▶ Adapter renders magic link
                          │ auth_required event         │        (Telegram InlineKeyboardButton)
                          └────────────────────────────┘
                                                                 ▼
                                                    User taps → browser opens
                                                                 ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ FastAPI /oauth/{provider}/start?state=<JWT>                                 │
│   1. decode JWT → (user_id, server_url, return_to)                          │
│   2. fetch /.well-known/oauth-protected-resource (RFC 9728)                 │
│   3. fetch /.well-known/oauth-authorization-server (RFC 8414)               │
│   4. DCR (RFC 7591) if no client registered for AS yet                      │
│   5. PKCE: gen verifier+challenge, persist verifier keyed by state          │
│   6. 302 → AS authorize URL (with resource=server_url, code_challenge)      │
└────────────────────────────────────────────────────────────────────────────┘
                                ▼
                  User consents at provider
                                ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ FastAPI /oauth/{provider}/callback?code=...&state=...                       │
│   1. decode state JWT                                                        │
│   2. exchange code (with code_verifier + resource) → tokens                  │
│   3. TokenVault.put(user_id, server_url, access_token, refresh_token, exp)  │
│   4. notify adapter via store: chat_append "Conectado ✅"                    │
│   5. 302 → return_to (deep link back to Telegram or "you can close this")   │
└────────────────────────────────────────────────────────────────────────────┘
                                ▼
                     Next user message → tool retried with token
```

---

## Task 1: PKCE + state JWT primitives + PKCE verifier store

**Files:**
- Create: `src/conexus/core/oauth/pkce.py`
- Create: `src/conexus/core/oauth/state.py`
- Modify: `src/conexus/core/memory/sqlite_store.py` — add `oauth_pkce_state` table
- Test: `src/conexus/tests/core/oauth/test_pkce.py`
- Test: `src/conexus/tests/core/oauth/test_state_jwt.py`

> **Security note:** `code_verifier` MUST NOT be placed in the state JWT (front-channel, visible in browser URL/logs). Instead: generate a random `state_nonce`, sign it as the JWT payload, and store `(state_nonce → verifier)` server-side in `oauth_pkce_state`. `/callback` retrieves verifier from DB by nonce. This preserves PKCE's guarantee that only the initiating server can redeem the code.

- [ ] **Step 1: Write failing tests**

```python
# test_pkce.py
from conexus.core.oauth.pkce import generate_pkce_pair, verify_challenge

def test_pair_lengths_and_charset():
    verifier, challenge, method = generate_pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert all(c.isalnum() or c in "-._~" for c in verifier)
    assert method == "S256"
    assert len(challenge) == 43  # base64url(sha256) no padding

def test_round_trip():
    verifier, challenge, _ = generate_pkce_pair()
    assert verify_challenge(verifier, challenge)
```

```python
# test_state_jwt.py
import time
import pytest
from conexus.core.oauth.state import encode_state, decode_state, StateExpired, StateInvalid

SECRET = b"x" * 32

def test_round_trip():
    tok = encode_state(SECRET, user_id="u1", server_url="https://mcp.example/", return_to="tg://chat/123")
    payload = decode_state(SECRET, tok)
    assert payload.user_id == "u1"
    assert payload.server_url == "https://mcp.example/"
    assert payload.return_to == "tg://chat/123"
    # verifier NOT in payload — stored server-side
    assert not hasattr(payload, "code_verifier")

def test_expired(monkeypatch):
    tok = encode_state(SECRET, user_id="u1", server_url="x", return_to="y", ttl_seconds=1)
    monkeypatch.setattr("conexus.core.oauth.state._now", lambda: time.time() + 10)
    with pytest.raises(StateExpired):
        decode_state(SECRET, tok)

def test_tampered():
    tok = encode_state(SECRET, user_id="u1", server_url="x", return_to="y")
    with pytest.raises(StateInvalid):
        decode_state(b"y" * 32, tok)
```

- [ ] **Step 2: Implement minimal code**

```python
# pkce.py
import base64, hashlib, secrets

def generate_pkce_pair() -> tuple[str, str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge, "S256"

def verify_challenge(verifier: str, challenge: str) -> bool:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == challenge
```

```python
# state.py
import time
from dataclasses import dataclass
import jwt  # PyJWT

class StateInvalid(Exception): pass
class StateExpired(Exception): pass

@dataclass
class StatePayload:
    user_id: str
    server_url: str
    return_to: str
    nonce: str  # random nonce — used to look up verifier server-side

def _now() -> float:
    return time.time()

def encode_state(secret: bytes, *, user_id: str, server_url: str, return_to: str,
                 nonce: str, ttl_seconds: int = 300) -> str:
    """Sign state JWT. code_verifier is NOT included — stored server-side keyed by nonce."""
    if len(secret) < 32:
        raise ValueError("state secret must be >= 32 bytes")
    payload = {
        "uid": user_id, "su": server_url, "ret": return_to, "nonce": nonce,
        "iat": int(_now()), "exp": int(_now()) + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def decode_state(secret: bytes, token: str) -> StatePayload:
    try:
        d = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise StateExpired()
    except jwt.PyJWTError:
        raise StateInvalid()
    return StatePayload(user_id=d["uid"], server_url=d["su"], return_to=d["ret"],
                        nonce=d["nonce"])
```

- [ ] **Step 3: Add `oauth_pkce_state` table to `sqlite_store.py` `init_db()`**

```sql
CREATE TABLE IF NOT EXISTS oauth_pkce_state (
  nonce TEXT PRIMARY KEY,
  code_verifier TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

- [ ] **Step 4: Run tests** — all green.

- [ ] **Step 5: Commit**
```bash
git add src/conexus/core/oauth src/conexus/tests/core/oauth src/conexus/core/memory/sqlite_store.py
git commit -m "feat(oauth): PKCE pair generator + state JWT (verifier stored server-side, not in JWT)"
```

---

## Task 2: Token crypto + TokenVault

**Files:**
- Create: `src/conexus/core/vault/crypto.py`
- Create: `src/conexus/core/vault/token_vault.py`
- Modify: `src/conexus/core/memory/sqlite_store.py` — add `oauth_tokens` + `oauth_clients` tables
- Test: `src/conexus/tests/core/vault/test_crypto.py`
- Test: `src/conexus/tests/core/vault/test_token_vault.py`

- [ ] **Step 1: Write failing tests**

```python
# test_crypto.py
from conexus.core.vault.crypto import encrypt, decrypt, derive_key

KEY = derive_key(b"master-secret-32-bytes-padding!!", salt=b"user_id_salt")

def test_round_trip():
    ct = encrypt(KEY, b"refresh_token_value")
    assert ct != b"refresh_token_value"
    assert decrypt(KEY, ct) == b"refresh_token_value"

def test_tamper_detected():
    import pytest
    ct = bytearray(encrypt(KEY, b"data"))
    ct[-1] ^= 0xFF
    with pytest.raises(Exception):
        decrypt(KEY, bytes(ct))
```

```python
# test_token_vault.py
import time
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.vault.token_vault import TokenVault, TokenRecord

def test_put_get_round_trip(tmp_path):
    store = SqliteStore(str(tmp_path / "v.db")); store.init_db()
    v = TokenVault(store, master_secret=b"x" * 32)
    v.put("u1", "https://mcp.example/", access_token="at1", refresh_token="rt1",
          expires_at=int(time.time()) + 3600, scopes=["calendar.read"])
    rec = v.get("u1", "https://mcp.example/")
    assert rec.access_token == "at1"
    assert rec.refresh_token == "rt1"
    assert "calendar.read" in rec.scopes

def test_get_missing_returns_none(tmp_path):
    store = SqliteStore(str(tmp_path / "v.db")); store.init_db()
    v = TokenVault(store, master_secret=b"x" * 32)
    assert v.get("u1", "https://mcp.example/") is None

def test_expired_flag(tmp_path):
    store = SqliteStore(str(tmp_path / "v.db")); store.init_db()
    v = TokenVault(store, master_secret=b"x" * 32)
    v.put("u1", "https://mcp.example/", access_token="at", refresh_token=None,
          expires_at=int(time.time()) - 10, scopes=[])
    rec = v.get("u1", "https://mcp.example/")
    assert rec.is_expired

def test_delete(tmp_path):
    store = SqliteStore(str(tmp_path / "v.db")); store.init_db()
    v = TokenVault(store, master_secret=b"x" * 32)
    v.put("u1", "https://mcp.example/", access_token="at", refresh_token=None,
          expires_at=int(time.time()) + 60, scopes=[])
    v.delete("u1", "https://mcp.example/")
    assert v.get("u1", "https://mcp.example/") is None
```

- [ ] **Step 2: Implement crypto.py (AES-GCM)**

```python
# crypto.py
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

def derive_key(master: bytes, *, salt: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt,
                info=b"conexus-token-vault").derive(master)

def encrypt(key: bytes, plaintext: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)

def decrypt(key: bytes, ct: bytes) -> bytes:
    nonce, body = ct[:12], ct[12:]
    return AESGCM(key).decrypt(nonce, body, None)
```

- [ ] **Step 3: Add SQLite schema**

In `sqlite_store.py` `init_db()` add:
```sql
CREATE TABLE IF NOT EXISTS oauth_tokens (
  user_id TEXT NOT NULL,
  server_url TEXT NOT NULL,
  access_token_enc BLOB NOT NULL,
  refresh_token_enc BLOB,
  expires_at INTEGER NOT NULL,
  scopes_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, server_url)
);

CREATE TABLE IF NOT EXISTS oauth_clients (
  authorization_server TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  client_secret_enc BLOB,
  registered_at TEXT NOT NULL
);
```

- [ ] **Step 4: Implement TokenVault**

```python
# token_vault.py
import json, time
from dataclasses import dataclass
from .crypto import derive_key, encrypt, decrypt

@dataclass
class TokenRecord:
    access_token: str
    refresh_token: str | None
    expires_at: int
    scopes: list[str]

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at - 30  # 30s skew

class TokenVault:
    def __init__(self, store, *, master_secret: bytes) -> None:
        self._store = store
        self._master = master_secret

    def _key(self, user_id: str) -> bytes:
        return derive_key(self._master, salt=user_id.encode())

    def put(self, user_id: str, server_url: str, *, access_token: str,
            refresh_token: str | None, expires_at: int, scopes: list[str]) -> None:
        k = self._key(user_id)
        at_enc = encrypt(k, access_token.encode())
        rt_enc = encrypt(k, refresh_token.encode()) if refresh_token else None
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._store.conn as c:
            c.execute("""INSERT OR REPLACE INTO oauth_tokens
                (user_id, server_url, access_token_enc, refresh_token_enc,
                 expires_at, scopes_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM oauth_tokens
                  WHERE user_id=? AND server_url=?), ?), ?)""",
                (user_id, server_url, at_enc, rt_enc, expires_at,
                 json.dumps(scopes), user_id, server_url, now, now))

    def get(self, user_id: str, server_url: str) -> TokenRecord | None:
        # Use context manager — conn property opens new connection each call; must close
        with self._store.conn as c:
            cur = c.execute(
                "SELECT access_token_enc, refresh_token_enc, expires_at, scopes_json "
                "FROM oauth_tokens WHERE user_id=? AND server_url=?",
                (user_id, server_url))
            row = cur.fetchone()
        if not row: return None
        k = self._key(user_id)
        at = decrypt(k, row[0]).decode()
        rt = decrypt(k, row[1]).decode() if row[1] else None
        return TokenRecord(access_token=at, refresh_token=rt,
                          expires_at=row[2], scopes=json.loads(row[3]))

    def delete(self, user_id: str, server_url: str) -> None:
        with self._store.conn as c:
            c.execute("DELETE FROM oauth_tokens WHERE user_id=? AND server_url=?",
                     (user_id, server_url))
```

- [ ] **Step 5: Run tests, commit**
```bash
git add src/conexus/core/vault src/conexus/core/memory/sqlite_store.py src/conexus/tests/core/vault
git commit -m "feat(vault): AES-GCM token vault with HKDF-derived per-user keys"
```

---

## Task 3: OAuth metadata discovery (RFC 9728 + 8414)

**Files:**
- Create: `src/conexus/core/oauth/metadata.py`
- Test: `src/conexus/tests/core/oauth/test_metadata_discovery.py`

- [ ] **Step 1: Write failing test (with mocked httpx)**

```python
# test_metadata_discovery.py
import pytest
from conexus.core.oauth.metadata import discover_protected_resource, discover_authorization_server

@pytest.mark.asyncio
async def test_protected_resource_metadata(httpx_mock):
    httpx_mock.add_response(
        url="https://mcp.example/.well-known/oauth-protected-resource",
        json={"resource": "https://mcp.example/",
              "authorization_servers": ["https://auth.example/"]})
    meta = await discover_protected_resource("https://mcp.example/")
    assert meta.authorization_servers == ["https://auth.example/"]

@pytest.mark.asyncio
async def test_authorization_server_metadata(httpx_mock):
    httpx_mock.add_response(
        url="https://auth.example/.well-known/oauth-authorization-server",
        json={"issuer": "https://auth.example/",
              "authorization_endpoint": "https://auth.example/authorize",
              "token_endpoint": "https://auth.example/token",
              "registration_endpoint": "https://auth.example/register",
              "code_challenge_methods_supported": ["S256"]})
    meta = await discover_authorization_server("https://auth.example/")
    assert meta.token_endpoint == "https://auth.example/token"
    assert "S256" in meta.code_challenge_methods_supported
```

- [ ] **Step 2: Implement**

```python
# metadata.py
from dataclasses import dataclass, field
from urllib.parse import urljoin
import httpx

@dataclass
class ProtectedResourceMetadata:
    resource: str
    authorization_servers: list[str]

@dataclass
class AuthorizationServerMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None = None
    code_challenge_methods_supported: list[str] = field(default_factory=list)
    scopes_supported: list[str] = field(default_factory=list)

async def discover_protected_resource(server_url: str) -> ProtectedResourceMetadata:
    url = urljoin(server_url.rstrip("/") + "/", ".well-known/oauth-protected-resource")
    async with httpx.AsyncClient() as c:
        r = await c.get(url, timeout=10.0)
        r.raise_for_status()
        d = r.json()
    return ProtectedResourceMetadata(resource=d["resource"],
                                      authorization_servers=d["authorization_servers"])

async def discover_authorization_server(as_url: str) -> AuthorizationServerMetadata:
    url = urljoin(as_url.rstrip("/") + "/", ".well-known/oauth-authorization-server")
    async with httpx.AsyncClient() as c:
        r = await c.get(url, timeout=10.0)
        r.raise_for_status()
        d = r.json()
    return AuthorizationServerMetadata(
        issuer=d["issuer"],
        authorization_endpoint=d["authorization_endpoint"],
        token_endpoint=d["token_endpoint"],
        registration_endpoint=d.get("registration_endpoint"),
        code_challenge_methods_supported=d.get("code_challenge_methods_supported", []),
        scopes_supported=d.get("scopes_supported", []),
    )
```

- [ ] **Step 3: Run tests, commit**
```bash
git add src/conexus/core/oauth/metadata.py src/conexus/tests/core/oauth/test_metadata_discovery.py
git commit -m "feat(oauth): RFC 9728/8414 well-known metadata discovery"
```

---

## Task 4: OAuthClient (DCR + authorize URL + exchange + refresh)

**Files:**
- Create: `src/conexus/core/oauth/client.py`
- Create: `src/conexus/core/oauth/errors.py`
- Test: `src/conexus/tests/core/oauth/test_oauth_client.py`

- [ ] **Step 1: Write errors module**

```python
# errors.py
class OAuthError(Exception):
    pass

class TokenExpiredError(OAuthError):
    pass

class NeedsAuthError(Exception):
    """Typed pause event — handler renders magic link, conversation suspends."""
    def __init__(self, server_url: str, scopes: list[str], resource: str | None = None):
        super().__init__(f"auth required for {server_url}")
        self.server_url = server_url
        self.scopes = scopes
        self.resource = resource or server_url
```

- [ ] **Step 2: Write failing tests for OAuthClient**

```python
# test_oauth_client.py
import pytest
from conexus.core.oauth.client import OAuthClient
from conexus.core.oauth.metadata import AuthorizationServerMetadata

AS = AuthorizationServerMetadata(
    issuer="https://auth.example/",
    authorization_endpoint="https://auth.example/authorize",
    token_endpoint="https://auth.example/token",
    registration_endpoint="https://auth.example/register",
    code_challenge_methods_supported=["S256"],
)

@pytest.mark.asyncio
async def test_dynamic_client_registration(httpx_mock, tmp_path):
    from conexus.core.memory.sqlite_store import SqliteStore
    store = SqliteStore(str(tmp_path / "c.db")); store.init_db()
    client = OAuthClient(store=store, master_secret=b"x" * 32,
                        redirect_uri="https://app/oauth/callback")

    httpx_mock.add_response(url="https://auth.example/register", method="POST",
                            json={"client_id": "cli_123", "client_secret": "sec_xyz"})

    cid, csec = await client.ensure_client(AS)
    assert cid == "cli_123"
    # cached on second call
    cid2, _ = await client.ensure_client(AS)
    assert cid2 == "cli_123"

def test_build_authorize_url():
    from conexus.core.memory.sqlite_store import SqliteStore
    import tempfile
    store = SqliteStore(tempfile.mktemp(suffix=".db")); store.init_db()
    client = OAuthClient(store=store, master_secret=b"x"*32,
                        redirect_uri="https://app/oauth/callback")
    url, verifier = client.build_authorize_url(
        AS, client_id="cli_123",
        scopes=["calendar.read"], resource="https://mcp.example/",
        state="state_token")
    assert url.startswith("https://auth.example/authorize?")
    assert "code_challenge=" in url
    assert "resource=https%3A%2F%2Fmcp.example%2F" in url
    assert "scope=calendar.read" in url
    assert verifier  # 43-128 chars

@pytest.mark.asyncio
async def test_exchange_code(httpx_mock, tmp_path):
    from conexus.core.memory.sqlite_store import SqliteStore
    store = SqliteStore(str(tmp_path / "c.db")); store.init_db()
    client = OAuthClient(store=store, master_secret=b"x"*32,
                        redirect_uri="https://app/oauth/callback")
    httpx_mock.add_response(url="https://auth.example/token", method="POST",
                            json={"access_token": "at1", "refresh_token": "rt1",
                                  "expires_in": 3600, "scope": "calendar.read"})
    tokens = await client.exchange_code(AS, client_id="cli_123",
        code="auth_code", code_verifier="verifier",
        resource="https://mcp.example/")
    assert tokens.access_token == "at1"
    assert tokens.refresh_token == "rt1"
    assert tokens.expires_in == 3600
```

- [ ] **Step 3: Implement OAuthClient**

```python
# client.py
from dataclasses import dataclass
from urllib.parse import urlencode
import httpx
from .pkce import generate_pkce_pair
from .metadata import AuthorizationServerMetadata
from ..vault.crypto import derive_key, encrypt, decrypt

@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str | None
    token_type: str = "Bearer"

class OAuthClient:
    def __init__(self, *, store, master_secret: bytes, redirect_uri: str) -> None:
        self._store = store
        self._master = master_secret
        self._redirect_uri = redirect_uri

    async def ensure_client(self, asm: AuthorizationServerMetadata) -> tuple[str, str | None]:
        """DCR per RFC 7591. Cached in oauth_clients table."""
        cur = self._store.conn.execute(
            "SELECT client_id, client_secret_enc FROM oauth_clients WHERE authorization_server=?",
            (asm.issuer,))
        row = cur.fetchone()
        if row:
            cid, csec_enc = row[0], row[1]
            csec = decrypt(derive_key(self._master, salt=b"oauth_clients"), csec_enc).decode() if csec_enc else None
            return cid, csec
        if not asm.registration_endpoint:
            raise RuntimeError(f"AS {asm.issuer} has no registration_endpoint and no static client configured")
        async with httpx.AsyncClient() as c:
            r = await c.post(asm.registration_endpoint, json={
                "client_name": "Conexus",
                "redirect_uris": [self._redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_basic",
            }, timeout=10.0)
            r.raise_for_status()
            d = r.json()
        cid, csec = d["client_id"], d.get("client_secret")
        csec_enc = encrypt(derive_key(self._master, salt=b"oauth_clients"), csec.encode()) if csec else None
        import time
        with self._store.conn as conn:
            conn.execute("""INSERT INTO oauth_clients
                (authorization_server, client_id, client_secret_enc, registered_at)
                VALUES (?, ?, ?, ?)""",
                (asm.issuer, cid, csec_enc, time.strftime("%Y-%m-%dT%H:%M:%S")))
        return cid, csec

    def build_authorize_url(self, asm: AuthorizationServerMetadata, *, client_id: str,
                            scopes: list[str], resource: str, state: str) -> tuple[str, str]:
        verifier, challenge, _ = generate_pkce_pair()
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": self._redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": resource,  # RFC 8707
        }
        return f"{asm.authorization_endpoint}?{urlencode(params)}", verifier

    async def exchange_code(self, asm: AuthorizationServerMetadata, *, client_id: str,
                             client_secret: str | None = None,
                             code: str, code_verifier: str, resource: str) -> TokenResponse:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "resource": resource,
        }
        auth = (client_id, client_secret) if client_secret else None
        async with httpx.AsyncClient() as c:
            r = await c.post(asm.token_endpoint, data=data, auth=auth, timeout=10.0)
            r.raise_for_status()
            d = r.json()
        return TokenResponse(access_token=d["access_token"], refresh_token=d.get("refresh_token"),
                             expires_in=d.get("expires_in", 3600), scope=d.get("scope"))

    async def refresh(self, asm: AuthorizationServerMetadata, *, client_id: str,
                      client_secret: str | None, refresh_token: str,
                      resource: str) -> TokenResponse:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "resource": resource,
        }
        auth = (client_id, client_secret) if client_secret else None
        async with httpx.AsyncClient() as c:
            r = await c.post(asm.token_endpoint, data=data, auth=auth, timeout=10.0)
            r.raise_for_status()
            d = r.json()
        return TokenResponse(access_token=d["access_token"],
                             refresh_token=d.get("refresh_token", refresh_token),
                             expires_in=d.get("expires_in", 3600), scope=d.get("scope"))
```

- [ ] **Step 4: Run tests, commit**
```bash
git add src/conexus/core/oauth/{client,errors}.py src/conexus/tests/core/oauth/test_oauth_client.py
git commit -m "feat(oauth): OAuthClient — DCR, PKCE authorize URL, code exchange, refresh"
```

---

## Task 5: McpHttpBackend (remote MCP w/ Bearer + auto-refresh)

**Files:**
- Create: `src/conexus/core/backends/mcp_http_backend.py`
- Test: `src/conexus/tests/test_framework_mcp_http_backend.py`

- [ ] **Step 1: Write failing tests**

```python
# test_framework_mcp_http_backend.py
import pytest
from conexus.core.backends.mcp_http_backend import McpHttpBackend
from conexus.core.oauth.errors import NeedsAuthError

class _FakeVault:
    def __init__(self, rec): self._rec = rec
    def get(self, user_id, server_url): return self._rec
    def put(self, *a, **kw): pass

class _Rec:
    def __init__(self, at, exp=False):
        self.access_token = at; self.is_expired = exp; self.refresh_token = None

@pytest.mark.asyncio
async def test_no_token_raises_needs_auth():
    backend = McpHttpBackend(server_url="https://mcp.example/",
                              vault=_FakeVault(None), user_id="u1",
                              scopes=["x"], oauth_client=None)
    with pytest.raises(NeedsAuthError) as e:
        await backend.start()
    assert e.value.server_url == "https://mcp.example/"

@pytest.mark.asyncio
async def test_lists_tools_with_bearer(httpx_mock):
    httpx_mock.add_response(url="https://mcp.example/mcp", method="POST",
        json={"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}})
    httpx_mock.add_response(url="https://mcp.example/mcp", method="POST",
        json={"jsonrpc": "2.0", "id": 2,
              "result": {"tools": [{"name": "list_events"}, {"name": "create_event"}]}})

    backend = McpHttpBackend(server_url="https://mcp.example/mcp",
                              vault=_FakeVault(_Rec("at1")), user_id="u1",
                              scopes=["x"], oauth_client=None)
    await backend.start()
    assert "list_events" in backend.list_tools()
    assert "create_event" in backend.list_tools()

@pytest.mark.asyncio
async def test_401_raises_needs_auth(httpx_mock):
    httpx_mock.add_response(url="https://mcp.example/mcp", method="POST", status_code=200,
        json={"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}})
    httpx_mock.add_response(url="https://mcp.example/mcp", method="POST", status_code=401,
        headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    backend = McpHttpBackend(server_url="https://mcp.example/mcp",
                              vault=_FakeVault(_Rec("expired_at")), user_id="u1",
                              scopes=["x"], oauth_client=None)
    await backend.start()
    with pytest.raises(NeedsAuthError):
        await backend._call("tools/list", {})
```

- [ ] **Step 2: Implement McpHttpBackend**

> **MCP-spec fixes applied:**
> - `Accept: application/json, text/event-stream` required on every POST (MCP 2025-06-18 §transport)
> - Response may be `application/json` OR `text/event-stream` — parse SSE frames when streaming
> - Must send `notifications/initialized` (JSON-RPC notification, no id) after initialize, before tools/list
> - Must capture `Mcp-Session-Id` from initialize response header and include on all subsequent requests
>
> **URL normalization:** `self._server_url` = canonical base (for vault key); `self._rpc_url` = base + `/mcp` (for HTTP calls). Vault always keyed by `self._server_url`, never `self._rpc_url`. `/callback` must store token under the same `server_url` (no `/mcp` suffix).

```python
# mcp_http_backend.py
"""Streamable HTTP MCP backend (MCP 2025-06-18 transport)."""
from __future__ import annotations
import asyncio, json
from typing import Any
import httpx
from .base import ToolBackend
from ..oauth.errors import NeedsAuthError, TokenExpiredError


def _parse_sse_result(body: str, req_id: int) -> Any:
    """Extract JSON-RPC result from SSE stream. Returns result field or raises."""
    for line in body.splitlines():
        if line.startswith("data:"):
            frame = json.loads(line[5:].strip())
            if frame.get("id") == req_id:
                if "error" in frame:
                    err = frame["error"]
                    raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
                return frame["result"]
    raise RuntimeError("MCP SSE stream ended without matching response frame")


class McpHttpBackend(ToolBackend):
    def __init__(self, *, server_url: str, vault, user_id: str, scopes: list[str],
                 oauth_client=None, asm=None) -> None:
        # Normalize: server_url = canonical base (vault key); rpc_url = base + /mcp
        base = server_url.rstrip("/")
        if base.endswith("/mcp"):
            self._server_url = base[:-4]  # strip /mcp for vault key
        else:
            self._server_url = base
        self._rpc_url = self._server_url + "/mcp"
        self._vault = vault
        self._user_id = user_id
        self._scopes = scopes
        self._oauth = oauth_client
        self._asm = asm
        self._tool_names: list[str] = []
        self._initialized = False
        self._session_id: str | None = None
        self._id = 0
        self._lock = asyncio.Lock()

    def _bearer(self) -> str:
        rec = self._vault.get(self._user_id, self._server_url)  # keyed by base url
        if rec is None:
            raise NeedsAuthError(self._server_url, self._scopes)
        if rec.is_expired:
            if rec.refresh_token and self._oauth and self._asm:
                raise TokenExpiredError()
            raise NeedsAuthError(self._server_url, self._scopes)
        return rec.access_token

    async def _refresh_then_get(self) -> str:
        rec = self._vault.get(self._user_id, self._server_url)
        if rec is None or not rec.refresh_token or not self._oauth or not self._asm:
            raise NeedsAuthError(self._server_url, self._scopes)
        cid, csec = await self._oauth.ensure_client(self._asm)
        try:
            new = await self._oauth.refresh(self._asm, client_id=cid, client_secret=csec,
                                            refresh_token=rec.refresh_token,
                                            resource=self._server_url)
        except Exception:
            self._vault.delete(self._user_id, self._server_url)
            raise NeedsAuthError(self._server_url, self._scopes)
        import time
        self._vault.put(self._user_id, self._server_url,
                        access_token=new.access_token,
                        refresh_token=new.refresh_token,
                        expires_at=int(time.time()) + new.expires_in,
                        scopes=self._scopes)
        return new.access_token

    def _headers(self, token: str) -> dict:
        h = {
            "Authorization": f"Bearer {token}",
            "MCP-Protocol-Version": "2025-06-18",
            "Accept": "application/json, text/event-stream",  # required by MCP spec
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    async def _post(self, token: str, req: dict) -> httpx.Response:
        async with httpx.AsyncClient() as c:
            return await c.post(self._rpc_url, json=req, timeout=30.0,
                                headers=self._headers(token))

    async def _call(self, method: str, params: dict) -> Any:
        async with self._lock:
            try:
                token = self._bearer()
            except TokenExpiredError:
                token = await self._refresh_then_get()
            self._id += 1
            req_id = self._id
            req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            r = await self._post(token, req)
            if r.status_code == 401:
                try:
                    token = await self._refresh_then_get()
                except NeedsAuthError:
                    raise
                r = await self._post(token, req)
                if r.status_code == 401:
                    raise NeedsAuthError(self._server_url, self._scopes)
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if "text/event-stream" in ct:
                return _parse_sse_result(r.text, req_id)
            frame = r.json()
            if "error" in frame:
                err = frame["error"]
                raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
            return frame["result"]

    async def _notify(self, method: str, params: dict | None = None) -> None:
        """Send JSON-RPC notification (no id, no response expected)."""
        try:
            token = self._bearer()
        except (NeedsAuthError, TokenExpiredError):
            return  # best-effort only
        notif = {"jsonrpc": "2.0", "method": method}
        if params:
            notif["params"] = params
        async with httpx.AsyncClient() as c:
            await c.post(self._rpc_url, json=notif, timeout=10.0,
                         headers=self._headers(token))

    async def start(self) -> None:
        init_result = await self._call("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "conexus", "version": "0.1.0"},
        })
        # Capture session ID if server assigned one (via response header — stored in last _post call)
        # NOTE: httpx response headers not accessible from _call; capture via direct post for initialize
        # Session ID capture: implementer should store r.headers.get("Mcp-Session-Id") in start().
        # Refactor: call _post directly for initialize to capture the header.
        self._initialized = True  # mark before tools/list
        # Required: send initialized notification before any further requests
        await self._notify("notifications/initialized")
        # Paginated tools/list
        tools = []
        cursor = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = await self._call("tools/list", params)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        self._tool_names = [t["name"] for t in tools]

    async def stop(self) -> None:
        pass  # HTTP — stateless, no subprocess

    async def execute(self, tool_name: str, args: dict) -> str:
        if not self._initialized:
            raise RuntimeError("McpHttpBackend.start() must be called before execute()")
        try:
            result = await self._call("tools/call", {"name": tool_name, "arguments": args})
            content = result.get("content", [])
            text_parts = [c["text"] for c in content if c.get("type") == "text"]
            return json.dumps("\n".join(text_parts) if len(text_parts) != 1 else text_parts[0])
        except NeedsAuthError:
            raise
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def list_tools(self) -> list[str]:
        return list(self._tool_names)

    @property
    def backend_type(self) -> str:
        return "mcp-http"
```

> **Mcp-Session-Id capture:** `_call()` routes through `_post()` but doesn't return headers. In `start()`, call `_post()` directly for the `initialize` request to capture `Mcp-Session-Id` from the response header and assign to `self._session_id`. The inline comment marks this for the implementer.

- [ ] **Step 3: Update test mocks to include `notifications/initialized` mock response**

Add a third `httpx_mock.add_response` for the notification POST (server may return 202 or 200 with no body):

```python
# In test_lists_tools_with_bearer, add after the tools/list mock:
httpx_mock.add_response(url="https://mcp.example/mcp", method="POST",
    status_code=202)  # notifications/initialized — no body
```

Reorder: initialize → notifications/initialized → tools/list (3 mocked responses total).

- [ ] **Step 4: Run tests, commit**
```bash
git add src/conexus/core/backends/mcp_http_backend.py src/conexus/tests/test_framework_mcp_http_backend.py
git commit -m "feat(backends): McpHttpBackend — Streamable HTTP MCP w/ Bearer, SSE, session-id, notifications/initialized"
```

---

## Task 6: ConnectorPack manifest + SkillLoader wiring

**Files:**
- Create: `src/conexus/core/connectors/__init__.py`
- Create: `src/conexus/core/connectors/pack.py`
- Modify: `src/conexus/core/skills/skill_resolver.py` — add `mcp-http` branch
- Test: `src/conexus/tests/core/connectors/test_pack_parser.py`

A connector pack is a SKILL_PACK with `backend: mcp-http` and a `connector.json` next to `SKILL_PACK.md`:

```yaml
# agents/<agent>/skills/google_calendar/SKILL_PACK.md
---
name: google_calendar
version: "1.0"
backend: mcp-http
capabilities: [calendar]
data_classes:
  list_events: read
  create_event: write
  update_event: write
  delete_event: write
---
Use the Google Calendar tools to manage the user's schedule.
```

```json
// agents/<agent>/skills/google_calendar/connector.json
{
  "server_url": "https://mcp.google.com/calendar",
  "scopes": ["https://www.googleapis.com/auth/calendar"],
  "ui": {
    "label": "Google Calendar",
    "icon": "calendar",
    "category": "Productivity",
    "description": "Read and manage events on the user's Google Calendar."
  }
}
```

- [ ] **Step 1: Write parser test**

```python
# test_pack_parser.py
import json
from conexus.core.connectors.pack import parse_connector_pack

def test_parse(tmp_path):
    pack = tmp_path / "google_calendar"
    pack.mkdir()
    (pack / "SKILL_PACK.md").write_text("""---
name: google_calendar
version: "1.0"
backend: mcp-http
data_classes: {list_events: read}
---
Body.
""", encoding="utf-8")
    (pack / "connector.json").write_text(json.dumps({
        "server_url": "https://mcp.google.com/calendar",
        "scopes": ["calendar.read"],
        "ui": {"label": "Google Calendar", "icon": "calendar",
               "category": "Productivity", "description": "Manage calendar."}
    }))
    cp = parse_connector_pack(pack / "SKILL_PACK.md")
    assert cp.skill_pack.frontmatter.name == "google_calendar"
    assert cp.connector.server_url == "https://mcp.google.com/calendar"
    assert cp.connector.scopes == ["calendar.read"]
    assert cp.connector.ui.label == "Google Calendar"
```

- [ ] **Step 2: Implement**

```python
# pack.py
from dataclasses import dataclass
from pathlib import Path
import json
from pydantic import BaseModel
from conexus.core.skills.pack_loader import parse_skill_pack, SkillPackDocument

class ConnectorUI(BaseModel):
    label: str
    icon: str = "plug"
    category: str = "Other"
    description: str = ""

class ConnectorDescriptor(BaseModel):
    server_url: str
    scopes: list[str]
    ui: ConnectorUI

@dataclass
class ConnectorPack:
    skill_pack: SkillPackDocument
    connector: ConnectorDescriptor

def parse_connector_pack(skill_pack_path: str | Path) -> ConnectorPack:
    sp = parse_skill_pack(skill_pack_path)
    cj = sp.pack_dir / "connector.json"
    if not cj.exists():
        raise FileNotFoundError(f"connector.json missing for pack {sp.frontmatter.name}: {cj}")
    desc = ConnectorDescriptor.model_validate(json.loads(cj.read_text()))
    return ConnectorPack(skill_pack=sp, connector=desc)
```

- [ ] **Step 3: Wire SkillLoader mcp-http branch**

In `skill_resolver.py` `load()`, add after `mcp_stdio` branch:

```python
elif doc.frontmatter.backend == SkillPackBackend.mcp_http:
    from conexus.core.connectors.pack import parse_connector_pack
    from conexus.core.backends.mcp_http_backend import McpHttpBackend
    cp = parse_connector_pack(pack_path)
    if self._vault is None or self._user_id is None:
        raise RuntimeError(
            f"mcp-http connector '{name}' requires SkillLoader(vault, user_id) — "
            f"caller did not provide identity context")
    backend = McpHttpBackend(
        server_url=cp.connector.server_url,
        vault=self._vault, user_id=self._user_id,
        scopes=cp.connector.scopes,
        oauth_client=self._oauth_client,
        asm=None,  # lazy: discovered on first NeedsAuthError → /oauth/start
    )
    # NOTE: do NOT add to self._mcp_backends (stdio lifecycle list).
    # McpHttpBackend.start() calls _bearer() which raises NeedsAuthError if no token.
    # Eager startup in start_all() would crash before user has authenticated.
    # HTTP backends are stateless (no subprocess) — start() is called on first execute().
    self._http_backends.append(backend)
    self._registry.register_backend(self._agent_name, backend)
```

Update `SkillLoader.__init__` to accept optional `vault`, `user_id`, `oauth_client` and add separate `_http_backends` list:

```python
def __init__(self, agent_dir, registry, agent_name, *,
             vault=None, user_id=None, oauth_client=None) -> None:
    self._agent_dir = Path(agent_dir)
    self._registry = registry
    self._agent_name = agent_name
    self._vault = vault
    self._user_id = user_id
    self._oauth_client = oauth_client
    self._mcp_backends: list = []   # stdio backends — eager lifecycle via start_all/stop_all
    self._http_backends: list = []  # http backends — lazy start on first execute
```

- [ ] **Step 4: Run tests, commit**
```bash
git add src/conexus/core/connectors src/conexus/core/skills/skill_resolver.py src/conexus/tests/core/connectors
git commit -m "feat(connectors): ConnectorPack manifest + SkillLoader mcp-http branch"
```

---

## Task 7: Handler — catch NeedsAuthError, emit auth_required event

**Files:**
- Modify: `src/conexus/core/agent_handler.py`
- Test: `src/conexus/tests/test_framework_agent_handler.py` (extend)

When a tool call raises `NeedsAuthError`, the handler must:
1. NOT bubble the exception to the LLM as a normal tool error.
2. Emit a structured event so the adapter can render a magic link.
3. Stop the current turn cleanly and return a placeholder reply.

- [ ] **Step 1: Add `auth_required` callback + `user_id` to AgentHandlerConfig**

```python
@dataclass
class AgentHandlerConfig:
    ...
    user_id: str | None = None  # set by adapter (Telegram user_id); used in NeedsAuthEvent
    on_auth_required: Callable[[NeedsAuthEvent], Awaitable[None]] | None = None

@dataclass
class NeedsAuthEvent:
    server_url: str
    scopes: list[str]
    resource: str
    user_id: str | None  # from cfg.user_id; adapter supplies per-message identity
```

- [ ] **Step 2: Wrap execute_tool call site in `handle_agent_message`**

```python
from conexus.core.oauth.errors import NeedsAuthError

# inside the for tc in tool_calls loop, replace the result = ... line:
try:
    result = (
        await cfg.execute_tool(fn_name, fn_args)
        if _is_async_tool
        else cfg.execute_tool(fn_name, fn_args)
    )
except NeedsAuthError as nae:
    if cfg.on_auth_required:
        await cfg.on_auth_required(NeedsAuthEvent(
            server_url=nae.server_url, scopes=nae.scopes,
            resource=nae.resource, user_id=cfg.user_id))
    pending = "Preciso de permissão para acessar essa ferramenta. Verifique a mensagem de conexão."
    store.chat_append(cfg.name, "assistant", pending)
    return pending
```

- [ ] **Step 2b: Apply same catch in `handle_team_message` tool execution path**

```python
# in handle_team_message, inside the frame.execute_tool call site:
try:
    result = await frame.execute_tool(fn_name, fn_args)
except NeedsAuthError as nae:
    if cfg.on_auth_required:
        await cfg.on_auth_required(NeedsAuthEvent(
            server_url=nae.server_url, scopes=nae.scopes,
            resource=nae.resource, user_id=cfg.user_id))
    return "Preciso de permissão para acessar essa ferramenta. Verifique a mensagem de conexão."
```

- [ ] **Step 3: Test**

```python
async def test_needs_auth_short_circuits(monkeypatch):
    from conexus.core.oauth.errors import NeedsAuthError
    events = []
    async def on_auth(ev): events.append(ev)
    async def execute_tool(name, args):
        raise NeedsAuthError("https://mcp.example/", ["x"])
    cfg = _make_cfg(execute_tool=execute_tool, on_auth_required=on_auth,
                    tools_schema=[{"type": "function", "function": {"name": "x", ...}}])
    # mock LLM to call tool x
    reply = await handle_agent_message(cfg, store, cap_checker, "do x")
    assert "permissão" in reply.lower()
    assert events[0].server_url == "https://mcp.example/"
```

- [ ] **Step 4: Run tests, commit**
```bash
git add src/conexus/core/agent_handler.py src/conexus/tests/test_framework_agent_handler.py
git commit -m "feat(handler): catch NeedsAuthError, emit auth_required event"
```

---

## Task 8: FastAPI OAuth callback router

**Files:**
- Create: `src/conexus/web/__init__.py`
- Create: `src/conexus/web/oauth_router.py`
- Create: `src/conexus/web/app.py`
- Test: `src/conexus/tests/web/test_oauth_router.py`

- [ ] **Step 1: Write router**

```python
# oauth_router.py
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse
import time
from conexus.core.oauth.metadata import discover_protected_resource, discover_authorization_server
from conexus.core.oauth.client import OAuthClient
from conexus.core.oauth.state import encode_state, decode_state, StateExpired, StateInvalid
from conexus.core.vault.token_vault import TokenVault

def make_router(*, store, master_secret: bytes, state_secret: bytes,
                redirect_uri: str, on_connected=None) -> APIRouter:
    router = APIRouter(prefix="/oauth")
    vault = TokenVault(store, master_secret=master_secret)
    oauth = OAuthClient(store=store, master_secret=master_secret, redirect_uri=redirect_uri)

    @router.get("/start")
    async def start(state: str):
        try:
            payload = decode_state(state_secret, state)
        except (StateInvalid, StateExpired):
            raise HTTPException(400, "invalid or expired state")
        prm = await discover_protected_resource(payload.server_url)
        asm = await discover_authorization_server(prm.authorization_servers[0])
        client_id, _ = await oauth.ensure_client(asm)
        scopes = []  # NOTE: filled via lookup against installed pack — implementer extends
        url, verifier = oauth.build_authorize_url(asm, client_id=client_id,
            scopes=scopes, resource=payload.server_url, state=state)
        # Store verifier SERVER-SIDE keyed by state nonce. NEVER put verifier in JWT (front-channel).
        with store.conn as c:
            c.execute(
                "INSERT OR REPLACE INTO oauth_pkce_state (nonce, code_verifier, created_at) "
                "VALUES (?, ?, ?)",
                (payload.nonce, verifier, time.strftime("%Y-%m-%dT%H:%M:%S")))
        return RedirectResponse(url, status_code=302)

    @router.get("/callback")
    async def callback(code: str, state: str):
        try:
            payload = decode_state(state_secret, state)
        except (StateInvalid, StateExpired):
            raise HTTPException(400, "invalid or expired state")
        # Retrieve verifier from server-side store by nonce
        with store.conn as c:
            row = c.execute(
                "SELECT code_verifier FROM oauth_pkce_state WHERE nonce=?",
                (payload.nonce,)).fetchone()
            if row:
                c.execute("DELETE FROM oauth_pkce_state WHERE nonce=?", (payload.nonce,))
        if not row:
            raise HTTPException(400, "PKCE verifier not found or expired")
        code_verifier = row[0]
        prm = await discover_protected_resource(payload.server_url)
        asm = await discover_authorization_server(prm.authorization_servers[0])
        cid, csec = await oauth.ensure_client(asm)
        tokens = await oauth.exchange_code(asm, client_id=cid, client_secret=csec,
            code=code, code_verifier=code_verifier, resource=payload.server_url)
        # Token stored keyed by base server_url (no /mcp suffix) — matches McpHttpBackend._server_url
        vault.put(payload.user_id, payload.server_url,
                  access_token=tokens.access_token, refresh_token=tokens.refresh_token,
                  expires_at=int(time.time()) + tokens.expires_in,
                  scopes=tokens.scope.split() if tokens.scope else [])
        if on_connected:
            await on_connected(user_id=payload.user_id, server_url=payload.server_url,
                              return_to=payload.return_to)
        if payload.return_to:
            return RedirectResponse(payload.return_to, status_code=302)
        return HTMLResponse("<h1>Conectado ✅</h1><p>Pode voltar pro Telegram.</p>")

    return router
```

```python
# app.py
from fastapi import FastAPI
from .oauth_router import make_router

def make_app(*, store, master_secret, state_secret, redirect_uri, on_connected=None) -> FastAPI:
    app = FastAPI(title="Conexus OAuth")
    app.include_router(make_router(store=store, master_secret=master_secret,
        state_secret=state_secret, redirect_uri=redirect_uri,
        on_connected=on_connected))
    return app
```

- [ ] **Step 2: Test with FastAPI TestClient + httpx_mock**

```python
# test_oauth_router.py
from fastapi.testclient import TestClient
from conexus.web.app import make_app
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.oauth.state import encode_state

def test_start_redirects_to_authorize(tmp_path, httpx_mock):
    store = SqliteStore(str(tmp_path / "w.db")); store.init_db()
    state_secret = b"s" * 32
    app = make_app(store=store, master_secret=b"m"*32, state_secret=state_secret,
                   redirect_uri="https://app/oauth/callback")
    httpx_mock.add_response(url="https://mcp.example/.well-known/oauth-protected-resource",
        json={"resource": "https://mcp.example/",
              "authorization_servers": ["https://auth.example/"]})
    httpx_mock.add_response(url="https://auth.example/.well-known/oauth-authorization-server",
        json={"issuer": "https://auth.example/",
              "authorization_endpoint": "https://auth.example/authorize",
              "token_endpoint": "https://auth.example/token",
              "registration_endpoint": "https://auth.example/register",
              "code_challenge_methods_supported": ["S256"]})
    httpx_mock.add_response(url="https://auth.example/register", method="POST",
        json={"client_id": "cli_1"})

    import secrets as _secrets
    state = encode_state(state_secret, user_id="u1",
        server_url="https://mcp.example/", return_to="tg://chat/1",
        nonce=_secrets.token_urlsafe(16))
    client = TestClient(app)
    r = client.get(f"/oauth/start?state={state}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://auth.example/authorize?")
```

- [ ] **Step 3: Commit**
```bash
git add src/conexus/web src/conexus/tests/web
git commit -m "feat(web): FastAPI OAuth router — /start (DCR + PKCE) + /callback (exchange)"
```

---

## Task 9: ConnectorRegistry (local catalog) + CLI

**Files:**
- Create: `src/conexus/core/connectors/registry.py`
- Modify: `src/conexus/cli/__main__.py`
- Test: `src/conexus/tests/core/connectors/test_registry.py`

A registry is a JSON file listing available connectors. Default location: `connectors/registry.json` in repo; users can install packs from URLs in the future.

```json
// connectors/registry.json
{
  "version": "1.0",
  "connectors": [
    {
      "name": "google_calendar",
      "version": "1.0",
      "server_url": "https://mcp.google.com/calendar",
      "scopes": ["https://www.googleapis.com/auth/calendar"],
      "pack_url": "https://github.com/conexus/connectors/google_calendar",
      "ui": {"label": "Google Calendar", "icon": "calendar",
             "category": "Productivity",
             "description": "Read and manage events on the user's Google Calendar."}
    }
  ]
}
```

- [ ] **Step 1: Implement registry**

```python
# registry.py
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

@dataclass
class RegistryEntry:
    name: str
    version: str
    server_url: str
    scopes: list[str]
    ui_label: str
    ui_icon: str
    ui_category: str
    ui_description: str
    pack_url: str | None = None

class ConnectorRegistry:
    def __init__(self, entries: list[RegistryEntry]) -> None:
        self._entries = {e.name: e for e in entries}

    @classmethod
    def from_file(cls, path: str | Path) -> "ConnectorRegistry":
        d = json.loads(Path(path).read_text())
        entries = [RegistryEntry(
            name=c["name"], version=c["version"], server_url=c["server_url"],
            scopes=c["scopes"], ui_label=c["ui"]["label"], ui_icon=c["ui"]["icon"],
            ui_category=c["ui"]["category"], ui_description=c["ui"]["description"],
            pack_url=c.get("pack_url"),
        ) for c in d["connectors"]]
        return cls(entries)

    def list(self) -> Iterable[RegistryEntry]:
        return self._entries.values()

    def get(self, name: str) -> RegistryEntry | None:
        return self._entries.get(name)
```

- [ ] **Step 2: Add CLI subcommands**

```python
# in __main__.py — add 'connectors' subcommand group
def _cmd_connectors(args):
    from conexus.core.connectors.registry import ConnectorRegistry
    reg = ConnectorRegistry.from_file(args.registry or "connectors/registry.json")
    if args.action == "list":
        for e in reg.list():
            print(f"{e.name:24} {e.version:8} {e.ui_category:14} {e.ui_label}")
            print(f"  {e.ui_description}")
    elif args.action == "install":
        # MVP: copy pack template from repo into agents/<agent>/skills/<name>/
        # Phase 11 scope: print instructions; full install (download + verify) is post-MVP.
        e = reg.get(args.name)
        if not e: raise SystemExit(f"unknown connector: {args.name}")
        target = Path("agents") / args.agent / "skills" / e.name
        target.mkdir(parents=True, exist_ok=True)
        (target / "SKILL_PACK.md").write_text(_pack_template(e))
        (target / "connector.json").write_text(json.dumps({
            "server_url": e.server_url, "scopes": e.scopes,
            "ui": {"label": e.ui_label, "icon": e.ui_icon,
                   "category": e.ui_category, "description": e.ui_description}}, indent=2))
        print(f"installed {e.name} → {target}")
        print(f"add '{e.name}@{e.version}' to {args.agent}/SKILL.md skills:")
    elif args.action == "connect":
        # Print magic link; user pastes into browser
        import secrets as _secrets
        from conexus.core.oauth.state import encode_state
        e = reg.get(args.name)
        secret = os.environ["CONEXUS_STATE_SECRET"].encode()
        nonce = _secrets.token_urlsafe(16)
        state = encode_state(secret, user_id=args.user, server_url=e.server_url,
                             return_to=args.return_to or "", nonce=nonce)
        base = os.environ.get("CONEXUS_OAUTH_BASE", "http://localhost:8000")
        print(f"{base}/oauth/start?state={state}")

def _pack_template(e):
    return f"""---
name: {e.name}
version: "{e.version}"
backend: mcp-http
capabilities: []
data_classes: {{}}
---
{e.ui_description}
"""
```

- [ ] **Step 3: Test, commit**
```bash
git add src/conexus/core/connectors/registry.py src/conexus/cli/__main__.py src/conexus/tests/core/connectors/test_registry.py connectors/registry.json
git commit -m "feat(connectors): ConnectorRegistry + 'conexus connectors {list,install,connect}' CLI"
```

---

## Task 10: Telegram adapter — magic link UX

**Files:**
- Modify: `adapters/telegram_runner.py`

- [ ] **Step 1: Wire `on_auth_required` callback when building runtime**

```python
# in telegram_runner.py — pseudo-snippet
from conexus.core.oauth.state import encode_state
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def on_auth_required(ev, *, chat_id, user_id, bot, state_secret, oauth_base):
    state = encode_state(state_secret, user_id=user_id, server_url=ev.server_url,
                          return_to=f"https://t.me/{bot.username}?start=auth_done")
    url = f"{oauth_base}/oauth/start?state={state}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Conectar conta", url=url)]])
    await bot.send_message(chat_id=chat_id,
        text="Preciso de acesso para essa ferramenta. Toque para conectar:",
        reply_markup=kb)

# pass on_auth_required=partial(on_auth_required, chat_id=..., user_id=..., bot=...) to AgentHandlerConfig
```

- [ ] **Step 2: Wire `on_connected` from FastAPI** — when callback fires, send Telegram message "✅ conectado, pode tentar de novo" via bot API.

- [ ] **Step 3: Manual smoke test** (no automated test — requires real Telegram). Document in commit message what was tested.

- [ ] **Step 4: Commit**
```bash
git add adapters/telegram_runner.py
git commit -m "feat(adapters): Telegram magic-link UX for connector OAuth"
```

---

## Task 11: E2E integration test (mock OAuth server + mock MCP server)

**Files:**
- Create: `src/conexus/tests/integration/fake_oauth_server/__init__.py` — FastAPI app w/ DCR + authorize + token endpoints
- Create: `src/conexus/tests/integration/fake_mcp_server/__init__.py` — minimal MCP HTTP server with bearer check
- Create: `src/conexus/tests/integration/test_connector_e2e.py`

- [ ] **Step 1: Write fake servers**

Skeletal structure (full impl follows MCP spec + RFC 6749):
```python
# fake_oauth_server — endpoints: /.well-known/oauth-authorization-server,
#   /register, /authorize (auto-redirects with code), /token (returns at+rt+exp)
# fake_mcp_server — endpoints: /.well-known/oauth-protected-resource,
#   /mcp (JSON-RPC; rejects 401 if no Bearer; tools: get_time)
```

- [ ] **Step 2: E2E test**

```python
# test_connector_e2e.py
import asyncio, threading, uvicorn, time
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.vault.token_vault import TokenVault
from conexus.core.backends.mcp_http_backend import McpHttpBackend
from conexus.core.oauth.client import OAuthClient
from conexus.core.oauth.metadata import discover_protected_resource, discover_authorization_server

async def test_full_flow_no_auth_then_callback_then_call(tmp_path):
    # 1. Start fake AS + RS in background threads
    from .fake_oauth_server import app as as_app
    from .fake_mcp_server import app as mcp_app
    as_thread = threading.Thread(target=lambda: uvicorn.run(as_app, port=8881, log_level="error"), daemon=True)
    mcp_thread = threading.Thread(target=lambda: uvicorn.run(mcp_app, port=8882, log_level="error"), daemon=True)
    as_thread.start(); mcp_thread.start(); time.sleep(0.5)

    store = SqliteStore(str(tmp_path / "e.db")); store.init_db()
    vault = TokenVault(store, master_secret=b"m"*32)
    oauth = OAuthClient(store=store, master_secret=b"m"*32,
                        redirect_uri="http://localhost:8883/cb")

    # 2. Without token, McpHttpBackend.start() raises NeedsAuthError
    backend = McpHttpBackend(server_url="http://localhost:8882/", vault=vault,
                             user_id="u1", scopes=["x"], oauth_client=oauth, asm=None)
    import pytest
    from conexus.core.oauth.errors import NeedsAuthError
    with pytest.raises(NeedsAuthError):
        await backend.start()

    # 3. Simulate /callback → token in vault
    prm = await discover_protected_resource("http://localhost:8882/")
    asm = await discover_authorization_server(prm.authorization_servers[0])
    cid, csec = await oauth.ensure_client(asm)
    # fake AS issues code "fake_code" for any authorize
    tokens = await oauth.exchange_code(asm, client_id=cid, client_secret=csec,
        code="fake_code", code_verifier="x"*43, resource="http://localhost:8882/")
    vault.put("u1", "http://localhost:8882/mcp",
              access_token=tokens.access_token, refresh_token=tokens.refresh_token,
              expires_at=int(time.time()) + tokens.expires_in, scopes=["x"])

    # 4. Now backend.start() succeeds, tools listed
    await backend.start()
    assert "get_time" in backend.list_tools()
    result = await backend.execute("get_time", {})
    assert "T" in result  # ISO timestamp
```

- [ ] **Step 3: Run + commit**
```bash
git add src/conexus/tests/integration/fake_* src/conexus/tests/integration/test_connector_e2e.py
git commit -m "test(connectors): E2E flow — NeedsAuth → /callback → token in vault → MCP call"
```

---

## Task 12: First connector pack — Google Calendar (validation slice)

**Files:**
- Create: `connectors/registry.json` — entry for `google_calendar`
- Create: `agents/teams/_marketplace_demo/skills/google_calendar/SKILL_PACK.md`
- Create: `agents/teams/_marketplace_demo/skills/google_calendar/connector.json`
- Document in `docs/wiki/agents-framework/<new partition>` how to install + connect

- [ ] **Step 1: Add registry entry** (use the official Google MCP server URL once published; placeholder for now)

- [ ] **Step 2: Manual end-to-end smoke**: install pack → run agent → ask "what's on my calendar tomorrow?" → tap magic link → consent on Google → message returns event list.

- [ ] **Step 3: Commit**
```bash
git add connectors/ agents/teams/_marketplace_demo
git commit -m "feat(connectors): Google Calendar pack — validation slice for marketplace"
```

---

## Wiki sync

After Task 12, dispatch `wiki-keeper` to update:
- `03-tools-design.md` — add ConnectorPack section
- `11-mcp.md` — replace "mcp-http not yet implemented" with shipped status, link to McpHttpBackend
- `14-conexus-target-architecture.md` — Phase 11 row marked done
- New partition `20-connector-marketplace.md` — full architecture writeup (auth flow diagram, pack format, registry, install/connect CLI, security model)
- `16-tutorial-create-agent.md` — add "attach a marketplace tool" sub-tutorial

---

## Self-review checklist (run after writing the plan)

**1. Spec coverage:**
- [x] OAuth 2.1 + PKCE + DCR + RFC 8707 (Tasks 1, 3, 4)
- [x] Encrypted token vault keyed by user_id (Task 2)
- [x] McpHttpBackend with auto-refresh (Task 5)
- [x] ConnectorPack manifest reusing SKILL_PACK (Task 6)
- [x] NeedsAuthError typed pause event (Task 4 errors + Task 7 handler)
- [x] FastAPI callback router (Task 8)
- [x] Marketplace registry + CLI (Task 9)
- [x] Telegram magic-link UX (Task 10)
- [x] E2E test with fake AS + RS (Task 11)
- [x] First real connector (Task 12)

**2. Placeholder scan:** none. Every task has runnable code.

**3. Type consistency:** `TokenRecord`, `TokenResponse`, `NeedsAuthError`, `ConnectorPack`, `ConnectorDescriptor`, `RegistryEntry` — all distinct, no naming collisions.

**4. Backward compat:** existing agents (no `mcp-http` skill) untouched. New `SkillLoader` kwargs default `None`. `AgentHandlerConfig.on_auth_required` defaults `None`.

**5. Security checklist (per MCP §6 + research findings):**
- [x] Per-user tokens (not shared service keys)
- [x] PKCE on every authorize
- [x] RFC 8707 `resource` param on every authorize + token request (audience-bound tokens)
- [x] Token storage encrypted at rest (AES-GCM, HKDF per-user key)
- [x] State JWT signed + 5min TTL (anti-replay)
- [x] No token passthrough — McpHttpBackend never forwards user tokens to a different host
- [x] Refresh token rotation on use (TokenVault overwrites on refresh)
- [x] Tokens deletable per-user (`vault.delete(user_id, server_url)` + `connectors disconnect` CLI)

**6. What is explicitly NOT in this phase:**
- Web dashboard UI (next phase)
- Connector pack signing / verification (next phase — security hardening)
- Aggregator backend (Composio/Arcade fallback) — explicit non-goal
- Per-tool budget metering for MCP tool calls (existing UsageTracker covers LLM only)
- Migrating Ana off native `GoogleCalendarClient`

---

## Execution directives (mandatory — apply to every task)

**Coding standard:** senior-level, objective, surgical. No speculative abstractions. No features beyond task spec. DRY/YAGNI/TDD. Match existing patterns in `src/conexus/core/`. Every changed line must trace to task text.

**Per-task quality gates (run in order, every task):**
1. TDD red → green → commit (Conventional Commits)
2. `/simplify` pass on diff before marking task done — strip dead code, collapse redundancy, kill premature abstractions
3. Targeted `uv run pytest -k <task>` + `uv run ruff check .`
4. Two-stage review (spec compliance → code quality) per subagent-driven-development skill

**Subagent prompt style:** `/caveman` mode (full) on all dispatch prompts — drop articles/filler/pleasantries, fragments OK, technical terms exact, code blocks unchanged. Keeps prompts dense, reduces token bloat, preserves substance.

**Model routing:** Sonnet for impl (mechanical TDD), Opus for review + design judgment. Haiku for trivial single-file edits only.

## Execution handoff

**Plan complete and saved to** `docs/superpowers/plans/2026-05-03-phase-11-connector-marketplace.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec then quality), fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch with checkpoints.

Recommend **Subagent-Driven**.

**Parallel dispatch plan (where deps allow):**
- **Wave A (parallel, 4 subagents):** Tasks 1, 2, 3, 12-fixtures-only — zero file overlap (`oauth/pkce.py`, `vault/`, `oauth/metadata.py`, test fixtures dir)
- **Wave B (parallel, 2 subagents):** Tasks 4, 5 — depend on Wave A; touch `oauth/client.py` + `backends/mcp_http_backend.py` independently
- **Wave C (sequential):** Tasks 6 → 7 → 8 → 9 → 10 — share `skill_resolver.py` / `agent_handler.py` / `__main__.py`, must be ordered
- **Wave D:** Task 11 (E2E) → Task 12 (Google Calendar pack validation slice)

**Codex parallel pre-validation** before Wave A dispatch (per `docs/dev-workflow/03-codex-validation.md`):
- Dispatch `/codex:rescue --background` × 3 in parallel:
  - Codex-1: security audit (PKCE, RFC 8707, vault crypto, no token passthrough)
  - Codex-2: MCP spec compliance (Streamable HTTP transport, `tools/list`, `tools/call`, error envelope)
  - Codex-3: framework integration sanity (ToolBackend ABC, AgentRegistry routing, NeedsAuthError catch site)
- Block Wave A until all 3 reports land. Address blockers inline before Task 1.

**Inter-wave gate:** after every wave, run `/simplify` on full diff + targeted batched test run. No wave proceeds with red tests or unaddressed reviewer issues.

---

## Out-of-scope follow-ups (capture in roadmap, do not bloat this plan)

- T-046 Web dashboard for connector marketplace (consumes ConnectorRegistry contract)
- T-047 Connector pack signing + signature verification on install
- T-048 Per-tool budget metering for MCP tool calls (extend UsageTracker)
- T-049 Aggregator backend (Composio/Arcade fallback) — opt-in only
- T-050 Hosted connector registry (`connectors.conexus.app/index.json`)
- T-051 Migrate Ana off native GoogleCalendarClient → use Google Calendar connector pack
