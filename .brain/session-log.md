# Last Session — Conexus
> Date: 2026-05-07 | Session: #7

## What Was Accomplished
- Phase 11 (Connector Marketplace) fully shipped — 13 tasks (T0-T12), 26 commits.
- OAuth 2.1 stack: PKCE S256, DCR (RFC 7591), RFC 8707 resource indicators, AS/PRM metadata discovery.
- AES-256-GCM TokenVault with HKDF-SHA256 per-purpose key derivation (domain-separated).
- McpHttpBackend: MCP 2025-06-18 Streamable HTTP, SSE parsing, session lifecycle, NeedsAuthError on no token.
- ConnectorPack manifest (SKILL_PACK + connector.json); SkillLoader mcp-http branch with lazy _http_backends.
- NeedsAuthEvent + on_auth_required callback wired into handle_agent_message + handle_team_message.
- FastAPI /oauth/start + /oauth/callback router; ConnectorRegistry + CLI (list/install/connect).
- Telegram magic-link callback factory (make_telegram_auth_callback).
- E2E integration test: fake OAuth AS + fake MCP server; NeedsAuth → vault → MCP call passes.
- Google Calendar validation connector pack + wiki sync (partitions 03, 11, 14, 16, new 20).

## What Changed in the System
- New: `src/conexus/core/oauth/` (pkce, state, metadata, client, errors)
- New: `src/conexus/core/vault/` (crypto, token_vault)
- New: `src/conexus/core/backends/mcp_http_backend.py`
- New: `src/conexus/core/connectors/` (pack, registry)
- New: `src/conexus/web/` (oauth_router, app)
- New: `src/conexus/adapters/telegram_auth.py`
- New: `connectors/registry.json`, `agents/teams/_marketplace_demo/skills/google_calendar/`
- Modified: SqliteStore (oauth_pkce_state, oauth_tokens, oauth_clients tables)
- Modified: SkillLoader (vault/user_id/oauth_client kwargs, _http_backends list)
- Modified: AgentHandlerConfig (user_id, on_auth_required); build_runtime passes through
- Modified: CLI __main__.py (connectors subcommand group)

## Decisions Made This Session
- PKCE verifier server-side only (oauth_pkce_state table, nonce in JWT) — ADR-002
- HKDF info domain separation: token vault uses b"conexus-token-vault", oauth clients use b"conexus-oauth-clients"
- URL normalization: _server_url = canonical base (vault key), _rpc_url = base + /mcp
- HTTP backends lazy start (not in _mcp_backends stdio lifecycle; start() on first execute)

## What's Immediately Next
- T-045: Migrate Ana to identity baseline (conexus-app repo — deferred per user, still planned)
- Push all local commits to remote (24+ commits ahead of origin, not yet pushed per user preference)
- Wire on_auth_required + user_id into actual Telegram bot message handler (real bot wiring, not just factory)

## Open Questions
- Google Calendar MCP server official URL (placeholder used; mcp.google.com/calendar not yet live)
- summarize_fn wiring for compactor (per-agent LLM or shared kernel default?)
