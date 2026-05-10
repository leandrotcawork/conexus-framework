# Memory & Wiki Architecture Design

> **Date:** 2026-05-08
> **Status:** Draft (brainstorming)
> **Author:** Leandro + Claude (with senior-review pass)

## Problem

The validator agent told "lembre que meu nome é Leandro" stored the name as a **note** (via the notes pack) instead of as a structured fact via `memory_set`. Inspecting the DB: `facts[validator]` empty, `identity_blocks` empty. The note workaround works in-session but doesn't surface in the framework's identity-fact injection (`inject_recent: 5`), so cross-session recall is unreliable.

Root causes:

1. No prompt guidance teaches the agent when to use `memory_set` (atomic identity), `wiki_write` (narrative/long-form), or notes pack (ephemeral lists). The notes-pack tool description looked applicable, the agent picked it.
2. Validator has no `identity.wiki` configured, so wiki tools error out — the agent has no narrative storage option even when it would be the right one.
3. Wiki backend is hardcoded to a git+SSH path with a deploy key in env. Fine for one production agent (Ana), wrong primitive for a framework that will grow to N agents and possibly N users.

This spec resolves all three for the new framework. Ana's existing Fly deployment is legacy and out of scope — it stays on its current SSH setup until separately migrated.

## Goals

- Agent reliably writes the right kind of memory to the right store on first try, without per-agent prompt customization.
- Wiki storage is pluggable. Adding a new backend doesn't touch agent code or identity tools.
- Production-quality auth path for remote wiki sync uses the same pattern Anthropic, OpenAI, Vercel, and Replit ship: GitHub App with installation tokens, no PATs, no SSH keys, no long-lived secrets.
- Per-agent isolation at the auth boundary. One agent's wiki cannot read another's.
- Greenfield framework. No SSH backend. No legacy compatibility shims.
- Phase 1 ships local-only and unblocks all current testing in hours, not days. Phase 2 (remote sync) ships later when distribution becomes a goal.

## Non-Goals

- Migrating Ana's existing Fly deployment. Separate effort.
- Async fact extraction from chat history. Phase 2+ work; spec'd separately when extractor design is ready.
- Vector search over facts or wiki. Premature at single-user scale; SQL `LIKE` and grep are sufficient until thousands of facts exist.
- Graph schema for facts. Hagoel's "memory is not a tree of concepts" applies; EAV with timestamps wins until proven insufficient.
- Multi-tenant SaaS encryption (KMS, audit log, rate limiting). Phase 3, may never come.

## Architecture

### Three storage layers, three purposes

| Layer | Lives in | Holds | Lifecycle | Tool surface |
|-------|----------|-------|-----------|--------------|
| **Facts** | `facts` table (SQLite) | Atomic key→value identity (`name`, `mother_name`, `daughter_name`, `favorite_color`, `birthday`) | Permanent until updated | `memory_set`, `memory_get`, `memory_list_facts`, `memory_delete` |
| **Wiki** | Pluggable backend (markdown files) | Narrative, projects, long-form notes, weekly digests | Permanent, append-friendly, organized by path | `wiki_write`, `wiki_read`, `wiki_list`, `wiki_search`, `wiki_append_log` |
| **Notes pack** | `pack_notes_entries` table | Ephemeral lists, todos, scratchpad | Created and consumed within a few sessions | `add_note`, `list_notes`, `delete_note` (pack-defined) |

The agent's job is to pick the right layer. The framework's job is to make that picking obvious.

### Decision 1 — Framework-default prompt guidance

When an agent has `identity.enabled: true`, the framework auto-prepends a system-prompt section explaining the three layers and when to use each. The section is the same across all identity-enabled agents, override-able if a specific agent needs different routing.

**Section template (pt-BR, since framework targets pt-BR agents):**

```
## Memória

Você tem três sistemas de memória:

1. **Fatos** (`memory_set`) — informações atômicas e permanentes sobre o usuário:
   nome, família, preferências, datas importantes, idioma. Use chave em snake_case.
   Exemplos: nome="Leandro", mãe="Maria", filha="Ana", cor_favorita="azul".

2. **Wiki** (`wiki_write`) — conteúdo narrativo, projetos, resumos, logs de pesquisa.
   Use quando a informação tem mais de uma frase ou precisa de estrutura.

3. **Notas** (pacote `notes`) — listas efêmeras, lembretes curtos, rascunhos.
   Use só quando o usuário pedir explicitamente "anote" ou "faça uma lista".

Regra: se o usuário compartilha algo sobre quem ele é ou quem está na vida dele,
SEMPRE use `memory_set`. Notas são para tarefas, não para identidade.
```

The text lives in `src/conexus/core/identity/prompt.py` as a constant. `assemble_identity_context` prepends it before facts/blocks/wiki sections when `identity.enabled`.

**Override:** if SKILL.md has `identity.prompt_override: ./custom_prompt.md`, the framework reads that file and substitutes. No code change needed for per-agent customization.

### Decision 2 — Tool surface clarity (notes pack)

The notes pack today exposes `add_note(text)` with a description that overlaps with "remember this for me." Update the pack's tool description so the model unambiguously picks facts when the input is identity-shaped:

```
add_note(text): "Adiciona uma anotação efêmera (lista, recado curto, rascunho).
NÃO use para informações pessoais permanentes (nome, família, preferências) —
para isso, use memory_set. NÃO use para conteúdo narrativo longo — use wiki_write."
```

Same for `list_notes`/`delete_note` if their descriptions invite confusion.

This is a description-only change in `packs/notes/`, no code logic touched.

### Decision 3 — Schema stays unchanged

`facts` table keeps `(agent_id, key, value, updated_at)` with `(agent_id, key)` primary key. Last write wins via `updated_at`.

`confidence`, `source`, `last_confirmed_at` are deferred to Phase 2 (async extractor PR), where their real requirements will drive the column choices. Adding them now without an extractor consumer means dead defaults today and likely schema rework when the extractor's actual needs emerge (`extracted_from_message_id`, `superseded_by`, etc. surfaced in research).

This reverses an earlier draft's "forward-looking schema" position. Reviewer correctly flagged it as YAGNI.

### Decision 4 — Pluggable wiki backend

```python
# src/conexus/core/memory/wiki/backend.py
from typing import Protocol

class WikiBackend(Protocol):
    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str) -> None: ...
    def list(self, folder: str = "") -> list[str]: ...
    def search(self, query: str) -> list[dict]: ...
    def exists(self, path: str) -> bool: ...
    def delete(self, path: str) -> None: ...
```

Two implementations:

**`LocalBackend` (Phase 1, ships now)**
- Plain directory at `agents/<name>/wiki/` (auto-created).
- No auth, no network, no git.
- `.gitignore` covers `agents/*/wiki/` so user wiki content doesn't leak into framework repo.
- Default for all new agents unless `backend: github_app` is set.

**`GitHubAppBackend` (Phase 2, deferred)**
- Per-agent repo: `<owner>/<agent-slug>-wiki`.
- App-based auth (see Auth section below).
- Local working copy at `agents/<name>/wiki/` cloned from repo on agent start, pushed on every write (or batched per minute), pulled before every read.
- Conflict policy: server wins. If a write fails because of a conflict, backend re-pulls and retries once. Second failure surfaces an error tool result the agent can decide what to do with.

`WikiStore` (existing class) becomes a thin facade: it picks the backend from `IdentitySection.wiki.backend` and delegates. Existing `wiki_*` tool methods don't change.

### Decision 5 — Per-agent repo model

Each agent that uses `github_app` backend gets its own GitHub repo: `<owner>/<agent-slug>-wiki`.

| Agent | Repo |
|-------|------|
| ana | `leandrotcawork/ana-wiki` (Phase 2 migration) |
| pesquisador | `leandrotcawork/pesquisador-wiki` |
| validator | `local` only (test agent, no remote) |
| custom future agent | `<owner>/<agent>-wiki` |

Hard isolation at the auth boundary. App is installed once per repo; revoking access for one agent doesn't affect others. Cross-agent knowledge sharing happens explicitly through `handoff_audit` table or `wiki_read` against another agent's wiki only when a tool is wired for it (not part of this spec).

Reviewer flagged per-agent repo as over-isolation at N=1. Decision is to accept the slight overhead at N=1 because the framework targets eventual multi-user, and auth-level isolation is fundamentally cheaper than retrofitting it later.

### Decision 6 — GitHub App auth model (Phase 2)

The professional pattern. Same as Anthropic Connectors, ChatGPT GitHub Connector, Vercel, Netlify, Replit Deploy.

**One-time setup (vendor side):**

1. Maintainer registers a GitHub App named "Conexus" via App Manifest (saves manual config).
   - Permissions: `contents:write`, `metadata:read`. Nothing else.
   - Webhook events: none (we pull, not push-triggered).
   - Callback URL: `https://<studio-host>/admin/oauth/github/callback`.
2. App private key generated and stored in Fly secrets as `GITHUB_APP_PRIVATE_KEY`.
3. App ID stored in Fly secrets as `GITHUB_APP_ID`.
4. App listed publicly so any user can install it on any repo they own.

**Per-agent install flow (in Studio admin UI):**

1. User clicks "Connect GitHub Wiki" on agent edit page.
2. Studio redirects to `https://github.com/apps/conexus/installations/new?state=<csrf>`.
3. User picks a repo (or creates one via App's `repo:create` permission), authorizes.
4. GitHub redirects back to `/admin/oauth/github/callback?installation_id=N&state=<csrf>`.
5. Studio verifies CSRF state (already-existing `oauth_pkce_state` table), then writes a row to `oauth_tokens`:
   ```
   (agent_id, provider='github_app', installation_id, repo_slug, created_at)
   ```
   No tokens stored. Just the installation_id and repo slug.
6. Studio writes `identity.wiki.backend: github_app` and `identity.wiki.repo: <owner>/<repo>` into the agent's SKILL.md.

**Per-request token minting:**

1. Backend calls `GitHubAppBackend.read(...)`. Backend needs an HTTP token.
2. Backend builds a JWT signed with `GITHUB_APP_PRIVATE_KEY`, expires in 9 minutes (App JWT max is 10).
3. Backend calls `POST /app/installations/{installation_id}/access_tokens` with the JWT.
4. GitHub returns an installation token, valid 1 hour, scoped to that one repo with `contents:write`.
5. Backend caches the token in-memory until 5 minutes before expiry, then re-mints.
6. Backend uses the token for `git clone` / `git push` / `git pull` operations against `https://x-access-token:<token>@github.com/<owner>/<repo>.git`.

**Why this beats PAT:**

- Token lifetime: 1 hour vs forever.
- Scope: one repo, one permission vs whatever PAT was scoped to (often broader than needed).
- Revocation: uninstall App from repo. PAT revocation requires user to find and revoke in their GitHub settings.
- Audit: every installation token use is logged on GitHub side under the App.
- Multi-user fit: each user installs the same App on their own repos. PAT means each user manages their own token, hard to support in a UI.

**Why this beats SSH deploy key:**

- Same lifetime/scope/revocation/audit advantages over PAT.
- No keypair generation, no `~/.ssh/known_hosts` trust dance, no per-deploy redeploy on key rotation.
- Standard HTTPS git protocol, works behind any firewall that allows GitHub.

**Why not OAuth user-to-server flow (act as the user):**

- Tokens are tied to a human's GitHub account; if user revokes the OAuth grant, all agents stop. App tokens are tied to the App, survive user-side OAuth changes.
- User-to-server tokens have broader default scope.
- Vendors who tried this (early Heroku, early Vercel) all migrated to App-based.

**Cost of building this:** ~1 day. App registration (10 min), OAuth callback route in Studio (~2hr), JWT + token mint helper (~2hr), `GitHubAppBackend` impl using `githubkit` (~3hr), tests (~1hr).

**Why not defer to Phase 3:** Phase 2 is when remote wiki sync becomes a real need (next agent that needs cross-device persistence, or first second-user). Building the auth layer at that point with the right primitive is cheaper than first shipping a PAT path and migrating off it later. PAT is a 30-line shortcut that becomes 30 lines of dead code plus migration work.

Reviewer flagged this as resume-driven design. Decision is to accept the half-day Phase 2 cost because: (a) the framework explicitly targets professional-pattern-from-start, (b) PAT-then-App migration is the worst-of-both-worlds path, (c) the actual code volume difference (PAT vs App backend) is ~150 lines, not the "30 vs 300" reviewer cited — reviewer was overestimating App complexity by counting OAuth UI + token mint as separate systems when they're standard library calls.

### Decision 7 — SKILL.md schema

```yaml
identity:
  enabled: true
  blocks:
    user:
      budget_chars: 500
    persona:
      budget_chars: 800
  facts:
    enabled: true
    inject_recent: 5
  wiki:
    backend: local                # default. or 'github_app'
    dir: ./wiki                   # for local. defaults to './wiki' relative to agent dir
    inject_index: true
    # for github_app:
    # repo: leandro/ana-wiki      # required
    # installation_id_from: db    # always loaded from oauth_tokens
  history:
    budget_tokens: 4000
    keep_verbatim: 6
    summary_budget: 800
    trigger_pct: 0.8
  prompt_override: null           # optional path to custom guidance markdown
```

`backend` defaults to `local`. If omitted, agent gets a local wiki at `agents/<name>/wiki/` auto-created.

For `github_app`, the YAML stays small. The `installation_id` is always looked up from `oauth_tokens` keyed on `(agent_id, provider='github_app')`. SKILL.md never holds a credential.

### File structure

**New files:**
- `src/conexus/core/memory/wiki/backend.py` — `WikiBackend` protocol
- `src/conexus/core/memory/wiki/local.py` — `LocalBackend` impl
- `src/conexus/core/memory/wiki/github_app.py` — `GitHubAppBackend` impl (Phase 2)
- `src/conexus/core/memory/wiki/auth.py` — JWT signing + token minting (Phase 2)
- `src/conexus/core/identity/prompt.py` — default prompt template constant
- `src/conexus/web/admin/routes/oauth_github.py` — OAuth callback (Phase 2)
- `src/conexus/tests/core/memory/test_wiki_local.py`
- `src/conexus/tests/core/memory/test_wiki_github_app.py` (Phase 2, mocked GitHub API)

**Modified files:**
- `src/conexus/core/memory/wiki_store.py` — becomes thin facade picking backend
- `src/conexus/core/identity/context.py` — prepends prompt template
- `src/conexus/core/config/skill_loader.py` — accepts new `backend` field, validates
- `src/conexus/cli/identity_runtime.py` — instantiates correct backend
- `packs/notes/skill.yaml` (or wherever tool descriptions live) — clearer descriptions
- `agents/validator/SKILL.md` — adds `identity.wiki.backend: local`
- `.gitignore` — ensure `agents/*/wiki/` ignored

**Removed files (greenfield):**
- Existing SSH-only logic in `wiki_store.py` migrates into a `LocalBackend` for the new framework. Ana's legacy Fly deployment keeps its own copy untouched. No `GitSSHBackend` shipped in new framework.

## Phasing

### Phase 1 — Local backend + prompt guidance + schema fix (ships now, ~3hr)

Goal: validator agent stores name in `facts` table on first try. All new agents have wiki out of the box.

Tasks:
1. Add `identity/prompt.py` with default guidance template.
2. Update `assemble_identity_context` to prepend it.
3. Define `WikiBackend` protocol.
4. Implement `LocalBackend`.
5. Refactor `WikiStore` to facade pattern over backends.
6. Add `backend` field to SKILL.md `IdentitySection`.
7. Update `IdentityRuntime` to instantiate correct backend.
8. Update notes pack tool descriptions.
9. Update validator SKILL.md to enable local wiki.
10. E2E test in Studio: validator stores name as fact, recalls across sessions, also writes a wiki page, also adds a note. All three end up in correct stores.
11. Update `.gitignore`.
12. Commit.

### Phase 2 — GitHub App backend (ships when remote sync needed, ~1 day)

Trigger condition: first agent that needs cross-device wiki sync, or distribution-readiness milestone.

Tasks:
1. Register Conexus GitHub App via manifest. Capture App ID and download private key. Store both in Fly secrets.
2. Add `auth.py` with JWT signing + installation-token minting. Cache tokens in-memory.
3. Add `GitHubAppBackend` using `githubkit` for API calls and stdlib `subprocess` for git operations against `https://x-access-token:...@github.com/...`.
4. Add OAuth callback route in Studio: `/admin/oauth/github/callback`. Verify CSRF state. Write `oauth_tokens` row.
5. Add "Connect GitHub Wiki" button to agent edit page.
6. Add "Disconnect" action that revokes the install (DELETE `/installation/repositories/{repo_id}`).
7. Tests with mocked GitHub API responses (use `respx` or `responses`).
8. Documentation: how a user installs the App on their repo.

### Phase 3 — Multi-tenant hardening (deferred indefinitely)

If/when Conexus becomes multi-user SaaS:
- Encrypt `oauth_tokens.installation_id` with Fly KMS or `cryptography.fernet` keyed off env secret.
- Add `wiki_audit (agent_id, action, path, ts)` table.
- Per-tenant rate limit on GitHub API calls (App-wide quota is 12.5k/hr).
- User-facing audit page showing every wiki read/write.

## Security

**Phase 1:**
- Local backend writes only inside `agents/<name>/wiki/`. Backend rejects paths with `..` or absolute paths.
- `.gitignore` ensures user wiki content stays out of framework repo.

**Phase 2:**
- App private key in Fly secrets only. Never logged. Never returned from any tool. Never serialized.
- CSRF protection via existing `oauth_pkce_state` table on OAuth callback.
- `oauth_tokens.installation_id` is not a credential by itself — it's an opaque ID that only becomes useful when combined with the App's signed JWT. Still, scoped to one repo per row.
- Studio admin UI shows only: backend type, repo slug, last sync time. Never raw tokens, never installation_id.
- Backend interface forbids exposing tokens via tool surface. `get_token()` is internal-only.
- Token cache lives in-process memory, never on disk.
- Git operations use `https://x-access-token:<token>@github.com/...` URL scheme. Token never written to `~/.git-credentials`.

**Phase 3:**
- See above.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Agent ignores prompt guidance, still uses notes for identity | Tool description audit (Decision 2) tightens the model's choice. If still bad, restrict notes pack tool surface when `identity.facts.enabled`. |
| `LocalBackend` data loss on Fly volume failure | Out of scope for Phase 1. Phase 2 GitHub App backend solves it for production agents. |
| GitHub App private key leak | Standard secret management. Fly secrets, never in code, never in logs. Rotate via App settings → "Generate new private key" → update Fly secret. Existing installations unaffected. |
| Token cache stale (token revoked but cached) | 5-minute pre-expiry refresh window means at most 5 minutes of stale token. Acceptable. If user uninstalls App, cached token returns 401, backend catches, surfaces clear error to agent. |
| Per-agent repo proliferation (many empty repos) | Only created when user clicks Connect for that agent. Validator/test agents stay local. |
| OAuth callback CSRF | Existing `oauth_pkce_state` table reused. State token verified before processing callback. |
| GitHub API rate limit | App-wide 12.5k requests/hour is plenty for single-user. Phase 3 adds per-tenant tracking when multi-user. |

## Testing strategy

**Phase 1:**
- Unit: `LocalBackend` read/write/list/search/exists/delete with tmpdir.
- Unit: path traversal rejection (`../`, absolute, symlinks).
- Unit: prompt template rendering for various SKILL.md configs.
- Integration: validator agent SKILL.md → start → call `wiki_write` → file appears in `agents/validator/wiki/`.
- E2E (Studio REPL): full flow — validator stores name as fact, writes a wiki entry, adds a note, all three correctly placed.

**Phase 2:**
- Unit: JWT signing with test private key.
- Unit: installation-token minting with mocked GitHub API.
- Unit: `GitHubAppBackend` git operations with mocked subprocess.
- Integration: full OAuth callback flow with mocked GitHub.
- Manual: real App install on real repo, end-to-end smoke test.

## Migration

Phase 1 is greenfield-friendly. New framework starts with this design. No migration of existing data needed — `facts` schema unchanged, validator wiki dir auto-created.

Ana's legacy Fly deployment is out of scope. When Ana migrates to the new framework (separate effort, separate spec), she'll install the Conexus App on her existing `ana-wiki` repo via the OAuth flow, drop her SSH deploy key from Fly secrets, and the GitHub App backend takes over. Zero data movement — same repo, different auth.

## Open Questions

None blocking Phase 1. For Phase 2:

1. App's `repo:create` permission — do we let Studio create repos for the user, or require user to create repo first? Default position: require user to create repo, simpler permission model, less surprise. Revisit if friction becomes real.
2. App naming — "Conexus" is taken on GitHub Marketplace? Need to check during App registration. Fallback names: "Conexus AI", "Conexus Agents".
3. App listed publicly on Marketplace, or private install-only? Private until distribution goal is concrete.

## Distilled principles (from research)

These guided the design and should guide future memory work:

1. **Async write, sync read** — never block a user reply on memory persistence.
2. **Validate on write, not on read** — contradiction-check at insertion time.
3. **EAV + scopes, not graphs first** — `(agent_id, key, value)` is the right primitive.
4. **Make memory inspectable and editable** — black-box memory is the #1 user complaint with ChatGPT memory.
5. **Budget memory at 5-10% of context** — top-k retrieval with hard token cap.
6. **Auth boundary > code boundary for isolation** — per-agent repo > shared-with-folder-check.
7. **App-based auth > PAT > SSH** for any system that will distribute.

## References

- Mem0 paper, arxiv 2504.19413 — async write, EAV with metadata, +26% accuracy vs ChatGPT memory at -90% token cost.
- A-Mem, arxiv 2502.12110 — Zettelkasten linking, 85-93% token reduction.
- MemGPT, research.memgpt.ai — paging metaphor (rejected here as overkill for single-user).
- Hagoel, "Why LLM Memory Still Fails" — graph schemas brittle, EAV wins.
- Mem0 State of Memory 2026 — practitioner consensus on schema patterns.
- GitHub Apps documentation — installation tokens, JWT auth, private key management.
- Vercel/Netlify/Replit GitHub integration — reference implementations of the App pattern.
