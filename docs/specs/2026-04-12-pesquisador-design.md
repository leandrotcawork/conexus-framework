# Pesquisador — Knowledge Researcher & Wiki Curator

> **Agent #2 for the Conexus infrastructure.** A 24/7 knowledge researcher that builds and maintains a professional software engineering knowledge wiki following Karpathy's LLM Wiki pattern. Communicates via Telegram in pt-BR.

---

## 1. Agent Identity

| Field | Value |
|-------|-------|
| **Name** | Pesquisador |
| **Role** | Knowledge researcher and wiki curator |
| **Language** | pt-BR |
| **Telegram prefix** | `pesq:` |
| **Budget** | $0.15/day, $4.50/month |

### LLM Tiers

| Tier | Model | Purpose |
|------|-------|---------|
| `primary` | `gemini/gemini-2.5-flash` | Queries, wiki lookups, web search summaries, digests — the workhorse |
| `synthesis` | `deepseek/deepseek-reasoner` (R1) | Wiki article compilation — turning raw sources into professional structured knowledge |

Each tier falls back to the other if the primary provider is down.

### Persona

- Professional and concise in wiki articles (Wikipedia-style: structured, factual, dense)
- Conversational in Telegram (pt-BR, matches Ana's tone)
- When asked a question: checks wiki first (cheap). If covered, answers from knowledge. If not, researches, writes the article, then answers.

---

## 2. Knowledge Wiki

### Repository

Separate Git repository: `knowledge-wiki` on GitHub. Not inside Conexus repo — the wiki is a standalone, permanent knowledge asset.

**Why separate repo:**
- Obsidian compatibility — clones directly into a vault later
- Multiple consumers — Claude Code, other agents, and Pesquisador all access it
- Survives infrastructure changes — not tied to any agent or Fly.io volume
- Clean git history of knowledge evolution

### Structure (Karpathy 3-Layer Pattern)

```
knowledge-wiki/
├── index.md                    # Master catalog — what exists, where
├── log.md                      # Append-only chronological record
├── schema.md                   # Rules for how articles are written
├── sources.md                  # Trusted source allowlist (Tier 1)
├── raw/                        # Layer 1: Immutable source material
│   ├── articles/               # Saved web articles
│   ├── transcripts/            # YouTube transcripts
│   └── pdfs/                   # Extracted PDF text
├── domains/                    # Layer 2: Compiled wiki (LLM-generated)
│   ├── backend/
│   │   ├── _index.md           # Domain overview + links to articles
│   │   ├── authentication/
│   │   │   ├── oauth2.md
│   │   │   ├── jwt.md
│   │   │   └── session-management.md
│   │   ├── databases/
│   │   ├── apis/
│   │   └── architecture/
│   ├── frontend/
│   ├── infrastructure/
│   ├── security/
│   ├── ai-ml/
│   ├── devops/
│   ├── languages/
│   │   ├── golang/
│   │   ├── python/
│   │   ├── typescript/
│   │   └── ...
│   └── ... (grows organically)
├── entities/                   # Specific tools/technologies
│   ├── postgresql.md
│   ├── docker.md
│   ├── fly-io.md
│   └── ...
└── concepts/                   # Cross-cutting ideas
    ├── twelve-factor-app.md
    ├── caching-strategies.md
    └── ...
```

**Layer 1 (raw/):** Immutable. Sources are never edited, only added. This is the evidence layer.

**Layer 2 (domains/, entities/, concepts/):** LLM-compiled knowledge. R1 synthesizes raw sources into structured articles. This is the knowledge layer.

**Layer 3 (schema.md, sources.md):** Governance. Tells the agent how to write, where to source, quality rules. This is the control layer.

### Article Format

No rigid template — the `schema.md` governs quality rules, not section names. Each article adapts to its topic. Required elements:

```markdown
---
domain: backend/authentication
confidence: high | medium | low
sources: 3
last_updated: 2026-04-12
---

# OAuth2

> One-sentence definition.

(Sections that make sense for THIS topic. OAuth2 needs "Flows" and
"Token Types". PostgreSQL needs "Data Types" and "Indexing". The
content adapts; the quality standard is constant.)

## See Also
- [[jwt]]
- [[session-management]]

## Sources
- raw/articles/oauth2-best-practices.md
- raw/transcripts/karpathy-security-talk.md
```

**Frontmatter fields:**
- `domain` — where this article lives in the tree
- `confidence` — high (3+ trusted sources), medium (1-2 sources or non-trusted), low (single source or outdated)
- `sources` — count of raw sources that informed this article
- `last_updated` — date of last compilation

### Index & Log

**index.md:** Master catalog. Every article listed with one-line summary, organized by domain. Updated on every write.

**log.md:** Append-only timeline. Format:
```
## [2026-04-12] ingest | OAuth2 — created domains/backend/authentication/oauth2.md from 4 sources
## [2026-04-12] update | JWT — added refresh token rotation section, confidence high→high
## [2026-04-13] audit | Found 3 low-confidence articles, 1 orphan page
```

### Organic Growth

The agent creates new domains, entities, and concepts automatically when researching topics that don't fit existing categories. If you ask about "game development" and `domains/gamedev/` doesn't exist, the agent creates it with its `_index.md` and the first article. The wiki grows to match your learning.

---

## 3. Source Trust System

### sources.md

A curated allowlist in the wiki repo. Three tiers control where the agent learns from.

**Tier 1: Trusted Sources (proactive research uses ONLY these)**

```markdown
## Official Documentation
- docs.python.org
- go.dev/doc
- react.dev
- developer.mozilla.org (MDN)
- postgresql.org/docs

## YouTube Channels
- Andrej Karpathy
- Fireship
- ThePrimeagen

## Blogs & Authors
- martinfowler.com
- blog.pragmaticengineer.com
- karpathy.ai

## Aggregators (top-rated only)
- news.ycombinator.com (Hacker News)
- github.com/trending
- awesome-* lists

## Communities
- dev.to (top rated)
- Specific subreddits (r/golang, r/python, etc.)
```

**Tier 2: User-Sent (always processed, no restrictions)**

Anything sent directly via Telegram — URLs, PDFs, YouTube links, GitHub repos, Instagram/Threads posts. You curate by sending.

**Tier 3: Web Search (constrained)**

On-demand research can search the open web, but:
- Prioritizes Tier 1 results
- Non-trusted sources get `confidence: low` in frontmatter
- Articles note "source not in trusted list"
- Proactive research NEVER uses Tier 3

### Managing Sources via Telegram

```
pesq: adicione canal Theo no YouTube
pesq: adicione site bytebytego.com
pesq: remova reddit r/programming
pesq: fontes                          # list current trusted sources
```

---

## 4. Tools

10 tools total, organized by function:

### Wiki Tools
| Tool | Signature | Purpose |
|------|-----------|---------|
| `wiki_read` | `(path: str) → str` | Read article from knowledge wiki |
| `wiki_write` | `(path: str, content: str) → str` | Create or update wiki article |
| `wiki_search` | `(query: str) → list[dict]` | Search wiki by keyword/topic |
| `wiki_list` | `(domain: str) → list[str]` | List articles in a domain |

### Research Tools
| Tool | Signature | Purpose |
|------|-----------|---------|
| `web_search` | `(query: str, sources_tier: int) → list[dict]` | Search the web via DuckDuckGo (duckduckgo-search), respecting source tiers. Free, no API key. Fallback: swap to Brave Search free tier if rate-limited |
| `web_fetch` | `(url: str) → str` | Fetch and extract article content from URL |
| `youtube_transcript` | `(url: str) → str` | Extract YouTube video transcript |
| `pdf_extract` | `(file_path: str) → str` | Extract text from PDF file |

### Storage Tools
| Tool | Signature | Purpose |
|------|-----------|---------|
| `raw_save` | `(category: str, filename: str, content: str) → str` | Save source material to raw/ |
| `git_sync` | `(message: str) → str` | Commit and push wiki changes to GitHub |

---

## 5. Telegram Interactions

### Commands

| Input | What happens | LLM tier |
|-------|-------------|----------|
| `pesq: pesquise OAuth2` | Research topic → save raw → compile wiki article → respond with summary | Flash + R1 |
| `pesq: o que é JWT?` | Check wiki first. If exists, answer from it. If not, research then answer | Flash (or +R1) |
| `pesq: resuma https://youtube.com/...` | Extract transcript → save raw → compile into wiki → respond | Flash + R1 |
| `pesq: resuma <PDF attached>` | Extract PDF text → save raw → compile into wiki → respond | Flash + R1 |
| `pesq: leia https://article.com/...` | Fetch article → save raw → compile into wiki → respond | Flash + R1 |
| `pesq: status` | Wiki stats: total articles, domains, recent additions, low-confidence count | Flash |
| `pesq: auditoria` | Audit wiki: contradictions, orphan pages, stale articles | Flash |
| `pesq: adicione <source>` | Add to trusted sources list | Flash |
| `pesq: fontes` | List current trusted sources | Flash |

### Response Format

After research + compilation:
```
Artigo criado: WebSockets
Dominio: backend/realtime
Fontes: 4 (2 trusted, 2 web)
Confianca: alta

Resumo: WebSockets provide full-duplex communication...
(3-4 line summary)

Wiki atualizada e sincronizada com GitHub.
```

After query (wiki hit):
```
JWT (JSON Web Token) é um padrão aberto (RFC 7519)...
(concise answer from wiki article)

Fonte: domains/backend/authentication/jwt.md
```

---

## 6. Scheduled Jobs

3 jobs, budget-conscious:

| Job | Cron | Description | Est. Cost |
|-----|------|-------------|-----------|
| `weekly_digest` | `0 20 * * 0` (Sunday 20:00) | Summary of what was added/updated this week, sent via Telegram | ~$0.01 |
| `wiki_audit` | `0 10 1 * *` (1st of month 10:00) | Scan for low-confidence, stale, contradictory, or orphan articles. Report findings | ~$0.02 |
| `proactive_research` | `0 14 * * 3,6` (Wed + Sat 14:00) | Pick 1 low-confidence or empty domain topic, research using Tier 1 sources only, improve wiki | ~$0.03 |

**No daily news digest** — burns tokens. Proactive research (2x/week) is the budget-friendly alternative. On-demand news is always available.

---

## 7. Integration with Conexus

### Shared Core (no changes needed)

- `core/messaging/telegram_bot.py` — add `pesq:` to `_split_prefix()`
- `core/llm/usage_tracker.py` — already tracks per-context costs
- `core/scheduler/scheduler.py` — already supports multiple agents' jobs
- `core/budget/` — budget enforcement per agent

### Shared Core (small additions)

- `core/llm/router.py` — no changes to TrackedLLM. Pesquisador gets two instances: `llm_primary` (Flash) and `llm_synthesis` (R1)
- `core/llm/pricing.py` — add DeepSeek R1 pricing entry
- `core/config/` — `parse_skill_file()` needs to read optional `llm_synthesis` block from frontmatter

### New Files (Ana's 3-file pattern)

| File | Purpose |
|------|---------|
| `agents/pesquisador/SKILL.md` | Frontmatter (name, llm tiers, schedules, budget) + system prompt |
| `agents/pesquisador/tools.py` | `PesquisadorTools` @dataclass — 10 tool methods |
| `agents/pesquisador/jobs.py` | 3 job builders: `make_weekly_digest_job`, `make_wiki_audit_job`, `make_proactive_research_job` |

### SKILL.md Frontmatter

```yaml
name: Pesquisador
role: Knowledge researcher and wiki curator
language: pt-BR
prefix: pesq

llm:
  provider: gemini
  model: gemini-2.5-flash
  temperature: 0.3

llm_synthesis:
  provider: deepseek
  model: deepseek-reasoner
  temperature: 0.2

schedules:
  - { kind: weekly_digest, cron: "0 20 * * 0" }
  - { kind: wiki_audit, cron: "0 10 1 * *" }
  - { kind: proactive_research, cron: "0 14 * * 3,6" }

budget:
  daily_usd: 0.15
  monthly_usd: 4.50
  on_exceed: notify
```

### Changes to main.py

- Parse Pesquisador's `SKILL.md` → build two TrackedLLM instances
- Instantiate `PesquisadorTools` with wiki repo path + web search client
- Add `_PESQUISADOR_TOOLS_SCHEMA` (10 tools in OpenAI format)
- Add `_handle_pesquisador_message` handler (same tool-calling loop as Ana)
- Register 3 jobs with scheduler

### Git Setup on Fly.io

- `knowledge-wiki` repo cloned to `/data/knowledge/` on startup
- GitHub deploy key (read/write) stored as Fly.io secret: `GITHUB_WIKI_DEPLOY_KEY`
- `git_sync` tool: `git add . && git commit -m "<message>" && git push`
- If clone doesn't exist on startup, `amain()` clones it

### New Secrets

| Secret | Purpose |
|--------|---------|
| `GITHUB_WIKI_DEPLOY_KEY` | SSH key for pushing to knowledge-wiki repo |
| `DEEPSEEK_API_KEY` | DeepSeek API key for R1 synthesis calls |
| *(none for search)* | Web search uses `duckduckgo-search` Python package — free, no API key needed |

---

## 8. Data Flow

### Research Flow (e.g., "pesq: pesquise WebSockets")

1. Telegram → `_split_prefix()` routes to Pesquisador handler
2. Flash checks wiki: does `domains/*/websockets.md` exist?
3. No → Flash searches web (prioritizing `sources.md` Tier 1)
4. Flash fetches 3-5 top articles, saves to `raw/articles/`
5. **R1** compiles raw sources into `domains/backend/realtime/websockets.md`
6. Flash updates `index.md` + domain `_index.md`
7. Flash appends to `log.md`
8. `git_sync` commits + pushes to GitHub
9. Flash sends summary via Telegram

### Query Flow (e.g., "pesq: o que é JWT?")

1. Flash checks wiki: `domains/backend/authentication/jwt.md` exists
2. Flash reads it, sends concise answer sourced from the article
3. No research, no R1, no web search — cheapest possible response

### Cost Optimization

Most daily interactions are queries (wiki lookup = Flash only). Research + compilation only fires when the wiki doesn't cover the topic. Over time, the wiki covers more → fewer research calls → costs naturally decrease.

---

## 9. Future Compatibility

### With Claude Code Workflow

The knowledge-wiki repo can be cloned locally alongside any project. Claude Code reads it during planning:
- "Check our wiki for auth best practices before designing this feature"
- "Does our wiki have anything on caching strategies?"
- Compare project implementation against wiki best practices

No direct integration needed — it's a Git repo. Any tool that reads files can use it.

### With Obsidian

The repo structure is Obsidian-compatible. To use as a vault:
1. Clone the repo
2. Open as Obsidian vault
3. `[[backlinks]]` in articles become navigable links
4. Frontmatter fields queryable via Dataview plugin
5. Graph view shows knowledge connections

### With Future Agents

A Sentinela (GitHub monitor) agent could reference the wiki: "This PR's auth implementation doesn't follow the OAuth2 best practices documented in the knowledge wiki." The wiki becomes shared infrastructure for all agents.

---

## 10. References

- [Karpathy's LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — original pattern
- [LLM Wiki v2](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2) — extended pattern with quality metadata
- [Obsidian Wiki (Ar9av)](https://github.com/Ar9av/obsidian-wiki) — Obsidian integration framework
- [VentureBeat: Karpathy's LLM Knowledge Base](https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an) — architecture overview
