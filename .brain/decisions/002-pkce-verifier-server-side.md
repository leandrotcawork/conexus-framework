# ADR-002: PKCE Verifier Stored Server-Side (Never in JWT)

**Date:** 2026-05-07
**Status:** accepted

## Context
Phase 11 OAuth flow needs a PKCE code_verifier that survives the browser redirect round-trip
(authorize → AS → /callback). The state JWT travels front-channel (URL, browser history, Referer
headers). Placing the verifier in the JWT exposes it publicly, breaking PKCE's security guarantee.

## Decision
The code_verifier is stored server-side in `oauth_pkce_state` (SqliteStore), keyed by a random
nonce. Only the nonce is embedded in the state JWT. `/oauth/start` writes nonce→verifier;
`/oauth/callback` reads and immediately deletes it.

## Rationale
PKCE's threat model assumes the verifier is secret (only the client that started the flow knows
it). Putting it in a signed JWT visible to the browser nullifies this protection. The server-side
table is inside the trusted execution boundary. Nonce provides the correlation without leaking.

## Consequences
- Requires `oauth_pkce_state` table in SqliteStore (added in this phase).
- Verifier TTL enforcement is manual (no automatic cleanup job yet — tech debt).
- Stateful: `/oauth/start` and `/oauth/callback` must hit the same DB instance (Fly single-region
  SQLite satisfies this; multi-region would need distributed state).

## Alternatives Considered
- Verifier in JWT (signed): rejected — front-channel exposure breaks PKCE threat model even with signing.
- Encrypted verifier in JWT: rejected — adds complexity without benefit; server-side is simpler and safer.
