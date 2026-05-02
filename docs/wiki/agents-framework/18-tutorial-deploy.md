# 18 — Tutorial: Deploy (Local + Fly.io)

Everything needed to run Conexus locally and ship it to Fly.io `gru`. After
this tutorial you can deploy without reading `deployment/` source files.

Cross-links: [[16-tutorial-create-agent]] (adding agents),
[[19-tutorial-runtime-flow]] (what boots and in what order).

---

## 1. Local development

### Prerequisites

- Python 3.11+ (the Dockerfile pins `python:3.11-slim`)
- `uv` package manager
- `.env` file at the repo root

### Quick start

```bash
uv sync                     # install deps from uv.lock
uv run pytest               # run the full test suite
uv run python main.py       # start both bots + scheduler
```

`main.py` is two lines — it calls `asyncio.run(run())` from
`adapters/telegram_runner.py` (see `main.py:1-11`).

### .env file

Create `.env` at the repo root. The runtime calls `load_dotenv()` at boot
(`adapters/telegram_runner.py:130`).

---

## 2. Environment variables reference

All vars read by the runtime. "Required" means startup fails without it.

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | — | Ana's Telegram bot token |
| `TELEGRAM_PESQ_BOT_TOKEN` | yes | — | Pesquisador's Telegram bot token |
| `AUTHORIZED_CHAT_ID` | yes | — | Integer Telegram user ID that the bots will accept messages from |
| `TELEGRAM_GROUP_CHAT_ID` | no | `""` | Comma-separated group chat IDs to also accept messages from |
| `GEMINI_API_KEY` | yes | — | Primary LLM for both agents |
| `GEMINI_MODEL` | no | per SKILL.md | Override model name (e.g. `gemini-2.5-flash`) |
| `OPENAI_API_KEY` | no | — | Fallback LLM chain |
| `ANTHROPIC_API_KEY` | no | — | Fallback LLM chain |
| `DEEPSEEK_API_KEY` | no | — | Fallback LLM chain |
| `GOOGLE_OAUTH_CLIENT_ID` | no | — | Google Calendar OAuth (Ana) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | no | — | Google Calendar OAuth (Ana) |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | no | — | Google Calendar OAuth (Ana) |
| `ANA_WIKI_REPO` | no | — | HTTPS URL of Ana's wiki git repo |
| `ANA_WIKI_DEPLOY_KEY` | no | — | PEM private key for Ana wiki SSH push (newlines as literal `\n`) |
| `KNOWLEDGE_WIKI_REPO` | no | — | HTTPS URL of Pesquisador's knowledge wiki repo |
| `GITHUB_WIKI_DEPLOY_KEY` | no | — | PEM private key for knowledge wiki SSH push |
| `CONEXUS_DATA_DIR` | no | `/data` (Fly) / `./data` (local) | Root for SQLite DB and wiki dirs |
| `CONEXUS_AGENTS_DIR` | no | `./agents` | Root of agent directories |
| `CONEXUS_MCP_TOKEN` | no | — | Bearer token for MCP server (required only if running `conexus mcp-server`) |
| `TZ` | no | `America/Sao_Paulo` | Set in Dockerfile; all cron times are BRT |

> Verified against `adapters/telegram_runner.py:130-305` and `deployment/fly.toml`.

### Local .env example

```bash
TELEGRAM_BOT_TOKEN=7123456789:AAFxxxx
TELEGRAM_PESQ_BOT_TOKEN=7987654321:AAByyy
AUTHORIZED_CHAT_ID=123456789
GEMINI_API_KEY=AIzaSy...
CONEXUS_DATA_DIR=./data
CONEXUS_AGENTS_DIR=./agents
```

Wiki repos and deploy keys are optional locally — skip them and wikis will use
`./data/wiki/` and `./data/knowledge/` as plain local directories.

---

## 3. Local data directories

```
./data/
  conexus.db          # SQLite — all chat_history, facts, todos, ping_log, llm_usage
  wiki/               # Ana's wiki (cloned from ANA_WIKI_REPO, or local)
  knowledge/          # Pesquisador's knowledge wiki
```

`CONEXUS_DATA_DIR` controls the root. `SqliteStore.__init__` takes
`db_path = data_dir / "conexus.db"` (see `adapters/telegram_runner.py:133`).

---

## 4. Fly.io deployment

### App topology

- App name: `conexus`
- Region: `gru` (São Paulo)
- Config: `deployment/fly.toml`
- Dockerfile: `deployment/Dockerfile`
- Persistent volume: `conexus_data` mounted at `/data`
- VM: `shared-cpu-1x`, `256mb` RAM (see `fly.toml:16-18`)

### Dockerfile walkthrough

`deployment/Dockerfile`:

```dockerfile
FROM python:3.11-slim

# git: wiki clone/push. openssh-client: deploy keys. gosu: drop to non-root.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client ca-certificates gosu \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 conexus

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

COPY deployment/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
COPY . .
RUN chown -R conexus:conexus /app

ENV PYTHONUNBUFFERED=1
ENV TZ=America/Sao_Paulo

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uv", "run", "python", "main.py"]
```

### Entrypoint

`deployment/entrypoint.sh`:

```sh
#!/bin/sh
set -e
mkdir -p /data
chown -R conexus:conexus /data   # Fly volumes mount as root; fix ownership
exec gosu conexus "$@"           # drop to non-root, then run CMD
```

The entrypoint ensures the Fly volume (`/data`) is writable by the `conexus`
user before the Python process starts.

---

## 5. Fly secrets checklist

Set all secrets with `fly secrets set KEY=value`. Secrets are injected as
environment variables at runtime — never in the Dockerfile.

### Required for basic operation

```bash
fly secrets set \
  TELEGRAM_BOT_TOKEN="..." \
  TELEGRAM_PESQ_BOT_TOKEN="..." \
  AUTHORIZED_CHAT_ID="123456789" \
  GEMINI_API_KEY="AIzaSy..."
```

### Required for Google Calendar (Ana)

```bash
fly secrets set \
  GOOGLE_OAUTH_CLIENT_ID="..." \
  GOOGLE_OAUTH_CLIENT_SECRET="..." \
  GOOGLE_OAUTH_REFRESH_TOKEN="..."
```

### Required for wiki git push

Deploy keys are PEM private keys. Newlines must be preserved. Use a heredoc
or a file:

```bash
# From file:
fly secrets set ANA_WIKI_DEPLOY_KEY="$(cat ~/.ssh/ana_deploy)"
fly secrets set GITHUB_WIKI_DEPLOY_KEY="$(cat ~/.ssh/pesquisador_deploy)"

# These vars name the HTTPS repo URLs (rewritten to SSH by telegram_runner.py):
fly secrets set ANA_WIKI_REPO="https://github.com/org/ana-wiki"
fly secrets set KNOWLEDGE_WIKI_REPO="https://github.com/org/knowledge-wiki"
```

### Optional LLM fallbacks

```bash
fly secrets set \
  OPENAI_API_KEY="sk-..." \
  ANTHROPIC_API_KEY="sk-ant-..." \
  DEEPSEEK_API_KEY="..."
```

### Optional MCP server

```bash
fly secrets set CONEXUS_MCP_TOKEN="$(openssl rand -hex 32)"
```

---

## 6. SSH key injection at startup

The runtime injects deploy keys automatically at boot
(`adapters/telegram_runner.py:42-127`).

For each wiki repo with a configured deploy key:

1. `_install_ssh_key(key_content, filename)` writes the PEM to
   `~/.ssh/{ana_deploy,pesquisador_deploy}` with mode `0o600`.
2. `ssh-keyscan -t ed25519 github.com` appends GitHub to `~/.ssh/known_hosts`.
3. `_clone_or_pull(repo_url, local_dir, key_file)` either clones (fresh) or
   pulls (existing) the wiki repo.
4. The HTTPS `ANA_WIKI_REPO` URL is rewritten to the SSH form
   `git@github.com:org/repo.git` when a key is present, and the git remote is
   updated in-place.

Nothing in this flow needs manual intervention after the secret is set.

### Sentinel file for clone safety

Before cloning into a non-empty directory, `_clone_or_pull` checks for a
`.conexus-clone-target` sentinel file. If the directory has files but no
`.git/` and no sentinel, it raises `RuntimeError` rather than silently
deleting your data. The sentinel is created after a successful clone
(`telegram_runner.py:89`).

---

## 7. Deploy command

```bash
# From the repo root:
fly deploy
```

Fly reads `deployment/fly.toml` (the `[build]` section points to
`deployment/Dockerfile`). The deploy strategy is `immediate` — zero-downtime
is not needed for a single-user bot.

### Volume

Create the volume once (if it does not exist):

```bash
fly volumes create conexus_data --size 1 --region gru
```

The volume persists across deploys. SQLite, wikis, and SSH sentinels all live
here.

---

## 8. MCP server (stdio, optional)

The MCP server (`src/conexus/core/mcp/producer.py`) is currently **not wired
into the Fly deployment**. It uses stdio transport, which requires a separate
process or HTTP transport to be network-accessible. Current scope: local use
with Claude Desktop.

To run locally:

```bash
CONEXUS_MCP_TOKEN=my-secret-token \
  conexus mcp-server --wiki-root ./data/wiki
```

This starts a FastMCP server on stdio exposing:

- `verify_bearer(token)` — client calls this first after `initialize`.
- `wiki_search(query)` — literal substring scan across `*.md` files, up to 20
  hits.
- `wiki://{path}` resource — raw markdown of a page, sandboxed to wiki root.

See `src/conexus/cli/__main__.py:102-109` for the CLI handler and
`src/conexus/core/mcp/producer.py:36` for `build_mcp_producer`.

---

## 9. Verifying the deployment

```bash
# Tail logs
fly logs

# Expected boot sequence output:
# [wiki] SSH deploy key configured (~/.ssh/ana_deploy)
# [wiki] Cloning https://github.com/... → /data/wiki...
# [wiki] Cloning https://github.com/... → /data/knowledge...
# Ana online (@<bot_username>).
# Pesquisador online (@<bot_username>).
```

If a bot does not come online within ~60 seconds, check logs for:

- `TELEGRAM_BOT_TOKEN` or `TELEGRAM_PESQ_BOT_TOKEN` missing → secrets not set.
- `GEMINI_API_KEY` missing → LLM fails on first call, not at startup; check
  after sending a message.
- SSH clone failure → verify the deploy key has read access to the repo and
  the HTTPS URL is correct.

---

## 10. Checklist

- [ ] `.env` created locally with all required vars
- [ ] `uv run python main.py` starts cleanly and bots come online
- [ ] `fly secrets set` done for all required vars
- [ ] `fly volumes create conexus_data` done (once)
- [ ] `fly deploy` succeeds
- [ ] `fly logs` shows both bots online
- [ ] Send a test message to each bot and confirm a reply
- [ ] (If wikis): wiki clone appears in `fly logs`; `wiki_read index.md` returns content
