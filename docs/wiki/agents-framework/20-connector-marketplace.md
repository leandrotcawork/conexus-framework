# 20 — Connector Marketplace

Remote MCP connector support shipped in Phase 11. This partition covers the
full stack: pack format, auth flow, vault, registry, CLI, and security model.

---

## 1. Executive summary

A **connector** is a remote MCP server accessed via OAuth 2.1. From the agent's
perspective it behaves like any other `ToolBackend` — the framework handles auth
invisibly. The user is only interrupted (magic-link inline keyboard) when no
valid token exists.

Key modules:

| Module | Path |
|--------|------|
| OAuth helpers (PKCE, state JWT, metadata discovery, DCR + code exchange + refresh) | `src/conexus/core/oauth/` |
| AES-GCM token vault + HKDF key derivation | `src/conexus/core/vault/` |
| MCP 2025-06-18 Streamable HTTP backend | `src/conexus/core/backends/mcp_http_backend.py` |
| ConnectorPack parser | `src/conexus/core/connectors/pack.py` |
| ConnectorRegistry (seed file) | `src/conexus/core/connectors/registry.py` · `connectors/registry.json` |
| FastAPI OAuth router (`/oauth/start`, `/oauth/callback`) | `src/conexus/web/oauth_router.py` |
| Telegram magic-link factory | `src/conexus/adapters/telegram_auth.py` |
| CLI commands | `src/conexus/cli/__main__.py` (`_cmd_connectors`) |

---

## 2. ConnectorPack format

A connector skill pack lives at `agents/<agent>/skills/<name>/` and contains
two files:

**`SKILL_PACK.md`** (standard frontmatter, `backend: mcp-http`)

```markdown
---
name: google_calendar
version: "1.0"
backend: mcp-http
capabilities: []
data_classes: {}
---
Read and manage Google Calendar events.
```

**`connector.json`** (parsed by `ConnectorDescriptor` in `src/conexus/core/connectors/pack.py`)

```json
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

`parse_connector_pack(skill_pack_path)` returns a `ConnectorPack(skill_pack,
connector)`. `server_url` doubles as the OAuth resource URI (RFC 8707) and as
the vault key used to look up stored tokens.

---

## 3. Auth flow

```
agent tool call
    │
    ▼ McpHttpBackend._bearer()
    │  vault.get(user_id, server_url) → None or expired?
    │  ├─ yes → raise NeedsAuthError(server_url, scopes)
    │  └─ no  → return access_token
    │
handle_agent_message catches NeedsAuthError
    │  cfg.on_auth_required(NeedsAuthEvent(...))
    │
make_telegram_auth_callback (src/conexus/adapters/telegram_auth.py)
    │  encode_state JWT → /oauth/start?state=<jwt>
    │  sends inline keyboard to Telegram user
    │
/oauth/start (FastAPI, src/conexus/web/oauth_router.py)
    │  1. decode_state → server_url, user_id, nonce
    │  2. discover_protected_resource (RFC 9728 /.well-known/oauth-protected-resource)
    │  3. discover_authorization_server (RFC 8414 /.well-known/oauth-authorization-server)
    │  4. OAuthClient.ensure_client → DCR (RFC 7591) or cached client_id
    │  5. build_authorize_url (PKCE S256, resource param RFC 8707)
    │  6. store (nonce, code_verifier) in oauth_pkce_state table
    │  7. redirect to AS authorization endpoint
    │
user grants consent in browser
    │
/oauth/callback (FastAPI, src/conexus/web/oauth_router.py)
    │  1. decode_state → nonce
    │  2. fetch code_verifier from oauth_pkce_state, delete row
    │  3. OAuthClient.exchange_code (PKCE + resource)
    │  4. TokenVault.put → encrypted tokens stored in oauth_tokens table
    │  5. on_connected callback (optional) → e.g. notify Telegram
    │  6. redirect return_to (Telegram deep-link)
    │
next tool call → vault hit → Bearer token injected
```

`NeedsAuthEvent` (`src/conexus/core/agent_handler.py:29`) carries `server_url`,
`scopes`, `resource`, and `user_id`. Both `handle_agent_message` and
`handle_team_message` catch `NeedsAuthError`
(`src/conexus/core/agent_handler.py:214` and `:443`).

---

## 4. Vault and cryptography

`TokenVault` (`src/conexus/core/vault/token_vault.py`) encrypts tokens at rest
using helpers from `src/conexus/core/vault/crypto.py`:

- **Key derivation:** HKDF-SHA256 via `cryptography.hazmat`. `derive_key(master,
  salt, info)` derives a 32-byte AES key. Two domains are used:
  - `info=b"conexus-token-vault"` (default) — per-user keys for `oauth_tokens`.
  - `info=b"conexus-oauth-clients"` — separate domain for client secret storage
    in `oauth_clients` table (`OAuthClient`, `src/conexus/core/oauth/client.py:24`).
- **Encryption:** AES-256-GCM. `encrypt(key, plaintext)` returns
  `nonce(12 bytes) + ciphertext+tag`. Tamper detection is guaranteed by GCM
  authentication tag; `decrypt` raises `InvalidTag` on any bit flip.
- **Per-user salt:** `TokenVault._key(user_id)` calls
  `derive_key(master, salt=user_id.encode())` — each user has a distinct AES
  key even though all rows share the same `master_secret`.

The `master_secret` must be provided at runtime (e.g. from env); it is never
stored in the database.

---

## 5. ConnectorRegistry and CLI

`ConnectorRegistry` (`src/conexus/core/connectors/registry.py`) loads
`connectors/registry.json` — a JSON file with a `connectors` array. The seed
registry ships with `google_calendar` (`connectors/registry.json`).

CLI commands (`conexus connectors <action>`):

| Command | What it does |
|---------|-------------|
| `conexus connectors list` | Print all connectors from the registry |
| `conexus connectors install <name> --agent <agent>` | Scaffold `SKILL_PACK.md` + `connector.json` under `agents/<agent>/skills/<name>/` |
| `conexus connectors connect <name> --user <id>` | Generate a one-shot `/oauth/start?state=<jwt>` URL for manual testing (requires `CONEXUS_STATE_SECRET` env var) |

`install` writes the pack files but does **not** modify `SKILL.md` — the
developer must add `<name>@<version>` to the `skills:` list manually.

---

## 6. Security model

- **PKCE S256.** `generate_pkce_pair()` (`src/conexus/core/oauth/pkce.py`) uses
  `secrets.token_bytes(32)` for the verifier, SHA-256 for the challenge. The
  verifier is stored server-side in `oauth_pkce_state` and deleted after one
  use — it never travels in the JWT state token.
- **State JWT.** `encode_state` / `decode_state` (`src/conexus/core/oauth/state.py`)
  use PyJWT with a short expiry. The state carries `server_url`, `user_id`,
  `nonce`, and `return_to`. The PKCE verifier is bound to the nonce via the
  `oauth_pkce_state` table, not the JWT.
- **RFC 8707 resource indicators.** `resource=server_url` is included in
  both the authorization URL and the token exchange. This scopes the issued
  token to a specific server, preventing token substitution attacks.
- **AES-GCM + HKDF domain separation.** See §4. Domain separation ensures that
  a key derived for one purpose (token storage) cannot decrypt ciphertexts
  produced for another purpose (client secret storage).
- **DCR (RFC 7591) — dynamic, not static.** Client credentials are registered
  per AS and cached in `oauth_clients`; client secrets are encrypted with the
  `conexus-oauth-clients` HKDF domain.
- **Token refresh on 401.** `McpHttpBackend` attempts a silent refresh
  (`OAuthClient.refresh`) before surfacing `NeedsAuthError`. On refresh failure
  the stale record is deleted from the vault to avoid infinite loops
  (`src/conexus/core/backends/mcp_http_backend.py:67`).

---

## 7. Validation connector pack

`agents/teams/_marketplace_demo/skills/google_calendar/` is the reference
connector pack used in integration tests. It demonstrates the minimal
`SKILL_PACK.md` + `connector.json` shape and can be used as a template.

---

## 8. Citations

- RFC 7591 — [OAuth 2.0 Dynamic Client Registration](https://www.rfc-editor.org/rfc/rfc7591)
- RFC 8414 — [OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- RFC 8707 — [Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- RFC 9728 — [OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [MCP Specification 2025-06-18 — Authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
