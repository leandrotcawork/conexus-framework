# 07 — RAG and Wiki-Based Knowledge for Agents

> Audience: senior engineers + Claude working on **Conexus**.
> Status: opinionated reference, 2026-05 snapshot.
> Premise: Conexus has a **pluggable markdown wiki** (Phase 1: `LocalBackend` — plain filesystem per agent, shipped 2026-05-08; Phase 2: `GitHubAppBackend` — GitHub App installation tokens + git subprocess sync, shipped 2026-05-08). Ana and Pesquisador read/write notes via `WikiStore`. There are **no embeddings yet** — retrieval today is filename routing + full-file reads. This document covers what RAG is in 2026, what's worth adopting, and what to stay away from until we need it.

---

## 1. Executive summary

RAG in 2026 is not a single thing. It's a spectrum that starts at "grep a folder and paste the result into the prompt" and ends at "a multi-agent system with graph reasoning, reranking, and self-critique loops." For Conexus, the important calibration is:

- **We are not a RAG product.** We are a personal agent with a ~few-hundred-file wiki. The working set fits in a single 200k-token context window. Naive file-read retrieval is *correct by default* until we have evidence it isn't.
- **The first upgrade is not embeddings.** It is (a) markdown-aware chunking, (b) BM25 lexical search, and (c) a retrieval-as-tool loop the agent can call iteratively. These give 80% of the benefit with 5% of the operational complexity.
- **Embeddings become worth it** when the wiki grows past ~2k notes, when cross-language synonym matching matters, or when the agent needs to answer conceptually ("what have I learned about burnout?") rather than lexically ("find the note about `wiki_store.py`").
- **Graphs (GraphRAG) are premature** for us. They pay off on enterprise corpora with rich entity relationships and global-sensemaking queries. Ana's wiki is personal, smaller, and query patterns are mostly local.
- **Git-backed markdown is a feature, not a constraint.** It gives us diffable state, human review, offline forks, and free version history. Any retrieval layer should treat `.md` files as ground truth and rebuild indices from them.

The rest of this document explains each layer so we can choose with our eyes open.

---

## 2. Naive RAG — and why it's often enough

Naive RAG is the textbook pipeline:

```
docs → chunk → embed → vector store
query → embed → top-k cosine → stuff into prompt → LLM answers
```

It's called "naive" pejoratively, but it's the baseline every serious system benchmarks against, and for a surprising number of workloads it wins. It wins when:

- The corpus is small enough that recall is not the bottleneck.
- Queries share vocabulary with the documents (same proper nouns, same code symbols).
- Chunks are already well-shaped (markdown with headers, code with function boundaries).
- The LLM has a large context window and can tolerate some irrelevant chunks.

For Conexus specifically, a *pre*-naive variant is already shipping: the agent has `wiki_list`, `wiki_read`, `wiki_search` tools and uses filenames + grep. This is fine. The honest upgrade path is:

1. Add markdown-aware chunking so `wiki_search` returns *sections*, not whole files.
2. Add BM25 on those chunks (see §4). `rank_bm25` in pure Python handles our scale.
3. Only then consider embeddings.

Do **not** skip steps 1 and 2 to go straight to a vector DB. You will spend a week on infra for a problem you didn't have.

---

## 3. Advanced RAG — techniques worth knowing

Once naive RAG hits a ceiling, these are the levers, roughly ordered by cost/benefit:

**Reranking.** The single highest-leverage addition. You retrieve top-50 cheaply (BM25 or dense), then a cross-encoder re-scores query+doc pairs jointly. 15–40% precision lift is typical. 2026 landscape: **Cohere Rerank v3.5 / v4** and **Zerank 2** lead hosted; **bge-reranker-v2-m3** (Apache 2.0, multilingual, ~50–100ms on GPU) is the default open-source pick; **jina-reranker-v3** is the sub-200ms-latency king. For Conexus, bge-reranker-v2-m3 running on CPU is fine at our scale; Cohere API if we want zero ops.

**Query rewriting.** The user's message is rarely a good retrieval query. An LLM rewrites it into 1–3 search queries. Cheap, high-ROI. Pair with the agent loop: let Claude itself write the queries — it already does, if you expose search as a tool.

**HyDE (Hypothetical Document Embeddings).** Instead of embedding the query, ask an LLM to *hallucinate an answer*, then embed that. Works because answers share vocabulary with answer-shaped documents, whereas questions don't. Overkill for us.

**Parent-child chunks (aka small-to-big).** Embed small chunks for retrieval precision, but return the *parent* chunk (or full document) to the LLM for context. Trivial to implement if chunks know their parent's ID. Strongly recommended once we chunk.

**Semantic chunking.** Split where embedding similarity drops, not on fixed token counts. Nicer boundaries, 2–5% retrieval lift, meaningful compute cost. Skip until measured.

---

## 4. Hybrid search — BM25 + dense + RRF

Dense vectors are bad at exact tokens. Ask a vector index for `wiki_store.py` and you may get back notes about "file storage" before the note literally named after that file. BM25 (lexical, TF-IDF family) nails proper nouns, code symbols, and rare terms. Dense wins on paraphrase and cross-language synonymy.

You want both. Fuse with **Reciprocal Rank Fusion (RRF)** — it's a one-liner, needs no score calibration:

```python
def rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1 / (k + rank)
    return dict(sorted(scores.items(), key=lambda x: -x[1]))
```

Feed it `[bm25_top50, dense_top50]`, take top-20, rerank, done. Qdrant, Weaviate, and Elasticsearch do this natively; with SQLite + `rank_bm25` you roll it yourself in ~30 lines.

**For Conexus**: BM25-only is the right first step. Our wiki is pt-BR with a lot of proper nouns (people, projects, tools). Lexical will carry us far.

---

## 5. GraphRAG — when graphs beat vectors

Microsoft's **GraphRAG** (2024) extracts entities + relations from a corpus with an LLM, clusters them into communities (Leiden), pre-summarises each community with an LLM, and at query time retrieves community summaries instead of chunks. It's designed for **global sensemaking** — "what are the themes in this corpus?" — where vectors fail because no single chunk contains the answer.

**LightRAG** (HKU, 2024) is the cheaper cousin: dual-level retrieval (entity-level + relation-level) without the expensive community-summary pre-compute. Usually second to GraphRAG in benchmarks but 10x cheaper to index. **LazyGraphRAG** (Microsoft, late 2024) delays graph construction to query time and beats full GraphRAG on the ICLR'26 GraphRAG-Bench suite while costing a fraction.

When graphs actually beat vectors:
- Corpus > 10k documents with rich entity overlap (legal, medical, intelligence).
- Queries are aggregative ("summarise all positions on X", "who collaborates with whom").
- You need to answer "unknown-unknowns" — questions the user couldn't have phrased with the right keywords.

When they don't:
- Personal wikis. Small knowledge bases. Queries that are local. This is us.

Revisit if Ana ever needs to answer "what have I been thinking about across all notes in the last year?" Until then, a graph is a liability: more infra, LLM cost to index, and a second source of truth that drifts from the markdown.

---

## 6. Agentic RAG — retrieval as a tool

This is the shape Conexus already has, and it's the shape everyone is converging on. Instead of a fixed `retrieve → generate` pipeline, retrieval is **a tool the agent calls**, possibly multiple times, possibly with self-critique between calls.

Patterns worth stealing:

- **Self-query.** The agent rewrites the user's message into a retrieval query before calling the tool. Our LLM already does this implicitly when it calls `wiki_search`.
- **Iterative retrieval.** First search returns 3 hits. Agent reads them, realises it needs date-scoped results, searches again. This is just good tool design — make sure `wiki_search` supports filters and the agent knows about them via the schema.
- **Self-critique / reflection.** After drafting an answer, the agent checks: "did I cite every claim? are any citations weak?" and re-retrieves for weak spots. Cheap with Claude; expensive with routing to a small model. Worth a system-prompt line for Ana, not a separate LLM call.
- **Plan-and-execute.** For research-heavy tasks (Pesquisador's `compile_article`), an explicit plan step ("I need 5 things: A, B, C, D, E") before parallel retrieval beats ad-hoc searching. Already implicit in Pesquisador's design — keep it.

The architectural point: **don't build a RAG pipeline alongside the agent.** Build retrieval tools the agent chooses. Conexus's `AgentRegistry` + tool-calling loop is exactly the right substrate.

---

## 7. Git-backed markdown wikis — the ecosystem

Our setup (markdown files in a git repo, pushed over SSH, read/written by agents) is quietly one of the best knowledge substrates available in 2026. Strengths:

- **Diffable.** Every change is reviewable. `git log -p` is an audit trail for free.
- **Forkable / syncable.** Clone on a laptop, edit offline, merge later. No API lock-in.
- **Portable.** Works with Obsidian, VS Code, `grep`, `cat`, any editor ever written.
- **Reviewable by humans.** Leandro can read and correct Ana's notes without touching code.
- **No schema drift.** The file is the truth. Indices can always be rebuilt.

Ecosystem worth watching:

- **Obsidian + agent plugins** — Obsidian Copilot, Smart Connections, Text Generator. The file format is identical to ours; Obsidian is purely a UI on top of a folder. You can open Ana's `/data/wiki/` in Obsidian today and get graph view, backlinks, and daily notes for free.
- **Foam** — VS Code extension, Obsidian-compatible wiki links, roam-style graph. Good if you prefer staying in VS Code.
- **Dendron** — hierarchical notes (`project.conexus.architecture.md`), schema-driven. More structure than we need but excellent for large knowledge bases.
- **Docusaurus + AI** — if you want to publish a subset of the wiki as a static site, Docusaurus with an MDX-aware RAG plugin is the 2026 default.
- **Quartz / Astro Starlight** — for public publishing with minimal ceremony.

For Conexus, the pragmatic stack is: **Obsidian as the human UI, git as transport (Phase 2), agents as collaborators.** We do not need a CMS.

**Phase 1 Conexus wiki architecture (shipped 2026-05-08).** The wiki layer is now pluggable:

- `WikiBackend` Protocol (`src/conexus/core/memory/wiki/backend.py:8`) — `@runtime_checkable`, six methods (`read/write/list/search/exists/delete`). `safe_join(root, relpath)` (line 20) is the path-safety contract: rejects `..`, absolute paths, backslashes, and symlink escapes.
- `LocalBackend` (`src/conexus/core/memory/wiki/local.py:9`) — plain filesystem impl. Auto-creates root dir. `list()` returns POSIX-relative paths. `search()` is substring grep with 120-char snippets. No auth, no network, no git.
- `WikiStore` (`src/conexus/core/memory/wiki_store.py`) — thin facade. `__init__` accepts `WikiBackend | str | Path`; `str/Path` builds a `LocalBackend` (back-compat shim). `WikiStore.local(root)` is the preferred factory.
- Backend is declared in SKILL.md: `identity.wiki.backend: local` (default) or `github_app`.
- Per-agent wiki directories live at `agents/<name>/wiki/` (excluded from git via `.gitignore` rule `agents/*/wiki/`).

**Phase 2 Conexus wiki architecture (shipped 2026-05-08).** `GitHubAppBackend` with remote sync is live:

- `git_auth.py` (`src/conexus/core/memory/wiki/git_auth.py`) — `_make_jwt(app_id, pem) -> str` builds a 9-minute RS256 JWT. `get_installation_token(app_id, pem, installation_id) -> str` wraps a module-level cache (`_TOKEN_CACHE: dict[int, tuple[str, float]]`) that evicts 5 minutes before expiry; on miss calls `POST https://api.github.com/app/installations/{id}/access_tokens` (sync `httpx`, 10 s timeout).
- `GitHubAppBackend` (`src/conexus/core/memory/wiki/github_app.py`) — implements `WikiBackend`. Composes `LocalBackend` for file I/O. All git operations run via `subprocess.run` (sync; blocks event loop — MVP acceptable, `asyncio.to_thread` deferred). `_ensure_clone()` clones on first use; on empty-repo failure falls back to `git init` + `git remote add origin`. `_refresh_remote()` rotates the installation-token URL before every network op (tokens are short-lived). `read/list/search/write/delete` all call `_pull()` before delegating to `LocalBackend`; `write` and `delete` additionally call `_commit_push()`. `exists()` is local-only (no pull).
- `github_app_installs` table in SQLite (`src/conexus/core/memory/sqlite_store.py:118`) — one row per agent: `(agent_id PK, repo_slug, installation_id, created_at)`. Helpers: `github_app_install_set/get/delete`.
- OAuth install flow: `GET /admin/oauth/github/start?agent=&repo=` → GitHub App install page; `GET /admin/oauth/github/callback?installation_id=&state=` → writes to `github_app_installs`, redirects to agent detail. Router: `make_github_wiki_router(store)` in `src/conexus/web/admin/routes/github_wiki.py`, registered in `make_admin_app` (`web/admin/app.py:65`). State nonce stored in `oauth_pkce_state.code_verifier` with `gh:` prefix to isolate from Phase 11 PKCE rows.
- `_build_wiki` in `src/conexus/cli/identity_runtime.py:45` dispatches the `github_app` branch: reads `github_app_install_get(agent_id)`, raises a human-readable `RuntimeError` if no row exists, reads `GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY` from env, builds `GitHubAppBackend(local_root=skill_dir/"wiki", ...)`.
- Known tech debt: `local_root=skill_dir/"wiki"` is inside the agent directory (not `/data`), which means wiki files do not survive Fly.io deploy image replacement. Needs to move to `data_dir/"wiki"` when deploying to Fly.

---

## 8. Embedding options — 2026

When embedding time comes, the shortlist:

| Model | Dim | Quality | Cost | Notes |
|---|---|---|---|---|
| **OpenAI text-embedding-3-large** | 3072 (MRL) | Strong baseline | $0.13/1M tok | Safe default if already on OpenAI |
| **Cohere Embed v4** | 1536 | Top-tier multilingual + images | $0.12/1M tok | Only major API with native text+image in same space |
| **Voyage-3.5 / voyage-3-large** | 1024/2048 | Best-in-class retrieval | Similar to OpenAI | Anthropic's recommended pairing with Claude |
| **Gemini Embedding 001 / 2** | 3072 | Top of MTEB (68.3 → 71+) | Generous free tier | Gemini 2 is multimodal (text/img/video/audio/PDF) |
| **bge-m3** (local) | 1024 | Strong multilingual, 100+ langs | Free, self-host | 568M params, Apache 2.0, the open-source default |
| **jina-embeddings-v3** (local) | up to 1024 MRL | Competitive, fast | Free / hosted | Good for long-context |
| **Qwen3-Embedding-8B** (local) | flexible 32–4096 | MTEB multilingual leader | Free, needs GPU | Bigger but top multilingual open-source |

MTEB scores shift every 3–4 months. The **rule**: re-benchmark the top 3 candidates on *your own* eval set every 6 months. Leaderboard rank is not production rank.

**For Conexus (pt-BR):** bge-m3 local if we self-host; Voyage-3.5 or Cohere Embed v4 if we want a hosted API. Gemini is attractive because we already have the API key.

---

## 9. Vector stores — 2026

The honest landscape:

- **Chroma** — easiest DX, great for local prototyping, deep LangChain ties. Fine up to ~1M vectors. Weak in production ops.
- **Qdrant** — Rust, open-source, strong filtering, rich query API, mature cloud. The "grown-up" default. Our pick if we outgrow SQLite.
- **pgvector** — vectors live in Postgres next to the rest of your data, same transaction, same backup. Excellent up to ~5M vectors; painful past ~50M. If you already have Postgres, use this.
- **LanceDB** — embedded, columnar (Lance format), zero-copy, disk-based. Think "SQLite for vectors." Great for larger-than-memory local workloads.
- **SQLite-VSS / sqlite-vec** — vector search inside SQLite. `sqlite-vec` is the 2026 successor, better indexing. Perfect for Conexus: we already have SQLite on `/data`, no new service.
- **DuckDB-VSS** — analytical vector search. Good when vectors sit alongside analytical data. Less common for agent RAG.

**For Conexus:** if/when we embed, **sqlite-vec** is the obvious choice. Lives next to `conexus.db`, zero new infrastructure, no Fly.io service to provision. Graduate to Qdrant only if we hit real scale or need advanced filtering.

---

## 10. Chunking strategies

Chunking is where most RAG systems silently lose quality. Choices, ordered from worst to best for markdown:

1. **Fixed-size (N tokens).** Shreds sentences and headings. Avoid.
2. **Recursive character split (LangChain default).** Tries separators in order (`\n\n`, `\n`, ` `). OK baseline.
3. **Sentence split.** Better than character, still ignores structure.
4. **Markdown-aware split.** Respects `#`/`##`/`###` boundaries; each chunk carries its header path as metadata. **This is the correct default for our wiki.**
5. **Semantic chunking.** Embedding-similarity-based boundaries. Nicer but costs embeddings at index time.

Practical recipe for Conexus:

```python
# pseudo-code
def chunk_markdown(path: Path) -> list[Chunk]:
    text = path.read_text()
    sections = split_by_headers(text)  # keep header path
    chunks = []
    for section in sections:
        if token_count(section.body) > 800:
            for sub in recursive_split(section.body, max_tokens=500, overlap=50):
                chunks.append(Chunk(
                    text=sub,
                    header_path=section.header_path,
                    source=path,
                    parent_section=section.id,  # for small-to-big
                ))
        else:
            chunks.append(Chunk(
                text=section.body,
                header_path=section.header_path,
                source=path,
                parent_section=section.id,
            ))
    return chunks
```

Always keep the **header path** in the chunk metadata — it's cheap context that massively helps the LLM.

---

## 11. Evaluation — Ragas, TruLens, and what actually matters

You cannot tune what you don't measure. Core metrics:

- **Context precision** — of retrieved chunks, how many are relevant?
- **Context recall** — of relevant chunks that exist, how many were retrieved?
- **Faithfulness / groundedness** — does the answer follow from the retrieved context, or does the LLM hallucinate?
- **Answer relevance** — does the answer actually address the question?

Tooling:

- **Ragas** — Python, LLM-as-judge, computes all four. The de-facto standard.
- **TruLens** — similar, with nicer dashboards and tracing. Good when you want observability, not just scores.
- **Promptfoo / DeepEval** — more general LLM eval frameworks with RAG modes.

The honest workflow: build a **50-question eval set by hand** from real Ana/Pesquisador interactions, check answers in once, then re-run Ragas on every retrieval change. Do not chase MTEB or benchmark-of-the-week. Your corpus is your benchmark.

---

## 12. Self-updating wiki — the hard part

This is where Conexus is ahead of most systems (Ana writes notes) and also where most of the unsolved problems live.

**Dedup.** Before writing, search for an existing note covering the same topic. Two layers:
- Lexical: exact title match, slug match.
- Semantic: top-k similar notes by embedding, threshold ~0.85.
If a similar note exists, the agent should *update* it, not create a new one.

**Conflict resolution.** Git gives us merge conflicts for free on the file level. Within a file, if Ana rewrites a note based on new info, keep the old version in git history — no in-file changelog needed. For contradictions ("I thought X, now I think Y"), prefer an explicit `## Update YYYY-MM-DD` subsection over silent overwrite. Humans (and future Anas) benefit from seeing the reasoning trail.

**Link-graph maintenance.** Markdown wiki-links (`[[note-name]]`) form a graph. When a note is renamed, update all inbound links. This is a small script, not AI. Run it as a pre-commit hook or as a scheduled agent job.

**Write policies.** Don't let the agent write freely. Minimum discipline:
- Every new note has YAML frontmatter: `created`, `updated`, `tags`, `source` (what triggered the note).
- Notes under some size threshold are "stubs" and flagged for consolidation.
- A weekly scheduled job reviews new notes: dedup check, link-graph repair, orphan detection.

**Trust gradient.** Notes Ana writes autonomously are lower-trust than notes Leandro has reviewed. Surface the distinction (a `reviewed: true` flag, or separate folders). When citing to the user, prefer reviewed notes.

---

## 13. Citations

When the agent answers from retrieved context, it must cite. Non-negotiable. Minimum:

```
...Leandro is working on Conexus' budget system [wiki/conexus/budget.md#L12-L34].
```

Implementation:

1. Every chunk carries `source_path` + `line_range` (or `header_path`).
2. The system prompt instructs the LLM to emit citations inline as `[source#anchor]`.
3. A post-processor validates citations resolve to real files and lines. If not, log + degrade gracefully.
4. For Telegram, render citations as short slugs; offer a "show sources" follow-up.

Citation hygiene is also a **hallucination alarm**. If the agent cites `wiki/foo.md` and that file doesn't exist, you have a grounding failure and should investigate, not silently strip it.

---

## Closing opinion

For Conexus, in this order:

1. **Don't build embeddings yet.** Add markdown-aware chunking + BM25 over chunks. Ship it.
2. **Add reranking** (bge-reranker-v2-m3 local, or Cohere API) once BM25's ceiling is visible.
3. **Add an eval harness** (Ragas, 50 questions) *before* the next retrieval change. Measure, don't guess.
4. **Add sqlite-vec embeddings** (bge-m3 or Voyage) when recall starts hurting — probably past 1k notes.
5. **Revisit GraphRAG** only if we start asking global/aggregative questions of the wiki. Today's query pattern doesn't justify it.
6. **Invest in the self-updating discipline** (dedup, link-graph, trust gradient, citations) regardless of which retrieval layer we're on. This is the part that compounds.

The wiki is the asset. Retrieval is replaceable plumbing.

---

## Sources

- [Ultimate Guide to Choosing the Best Reranking Model in 2026 — ZeroEntropy](https://www.zeroentropy.dev/articles/ultimate-guide-to-choosing-the-best-reranking-model-in-2025)
- [Best Rerankers for RAG — Agentset Leaderboard](https://agentset.ai/rerankers)
- [Smaller, Faster, Cheaper: Jina Rerankers Turbo and Tiny](https://jina.ai/news/smaller-faster-cheaper-jina-rerankers-turbo-and-tiny/)
- [BenchmarkQED: Automated benchmarking of RAG systems — Microsoft Research](https://www.microsoft.com/en-us/research/blog/benchmarkqed-automated-benchmarking-of-rag-systems/)
- [When to use Graphs in RAG — ICLR'26 / GraphRAG-Bench](https://arxiv.org/html/2506.05690v3)
- [GraphRAG-Bench repository](https://github.com/GraphRAG-Bench/GraphRAG-Benchmark)
- [Graph RAG in 2026: What Works in Production — paperclipped.de](https://www.paperclipped.de/en/blog/graph-rag-production/)
- [Best Embedding Models for RAG (2026) — Prem AI](https://blog.premai.io/best-embedding-models-for-rag-2026-ranked-by-mteb-score-cost-and-self-hosting/)
- [Embedding Model Leaderboard: MTEB March 2026](https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-march-2026/)
- [Voyage 3.5 vs OpenAI vs Cohere Embedding Models 2026](https://www.buildmvpfast.com/blog/best-embedding-model-comparison-voyage-openai-cohere-2026)
- [Vector Database Comparison 2026 — 4xxi](https://4xxi.com/articles/vector-database-comparison/)
- [Best Vector Databases in 2026 — Firecrawl](https://www.firecrawl.dev/blog/best-vector-databases)
- [Vector databases: trade-offs — The Data Quarry](https://thedataquarry.com/blog/vector-db-4/)
