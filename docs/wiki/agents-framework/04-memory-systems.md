# 04 — Memory Systems for Agents

> Audience: senior engineer + Claude working on Conexus. Conexus today has a SQLite message store (`core/memory/sqlite_store.py`) for conversation logs and a git‑backed markdown wiki (`core/memory/wiki_store.py`) as long‑term knowledge. This doc is the reference for deciding what to keep, what to adopt, what to replace.

---

## 1. Executive summary

An LLM on its own is stateless: every call re‑reads whatever you jam into the context window. "Agent memory" is the plumbing that turns a sequence of stateless calls into an entity with continuity. In 2025–2026 the field has converged on a small set of patterns and a larger set of implementations:

- **MemGPT/Letta** — agent self‑edits "core blocks" in context; overflow goes to archival (vector DB) and recall (message log). Sleep‑time agents do async consolidation.
- **Mem0** — an LLM extraction+update pipeline that distils conversations into atomic facts stored in a vector DB with explicit ADD/UPDATE/DELETE/NOOP operations. Reports 26% accuracy gain over OpenAI memory on LOCOMO with 90% fewer tokens.
- **Zep/Graphiti** — bitemporal knowledge graph (event time + ingestion time) with edge invalidation. 94.8% on DMR, 18.5% accuracy over MemGPT baseline, 90% lower latency.
- **A‑MEM** — Zettelkasten‑style self‑linking notes: each memory is a structured markdown note with tags/keywords, linked to semantically related notes.
- **Karpathy LLM‑wiki pattern** — agent incrementally edits a human‑readable markdown wiki; retrieval by BM25+vector+rerank (e.g. `qmd`).

**Conexus recommendation preview (detail in §13):** keep SQLite for raw messages, keep markdown wiki for durable semantic memory (it is your strongest asset), but add (a) a Mem0‑style extraction layer that writes into the wiki with ADD/UPDATE/DELETE semantics, (b) a small embedding index over wiki files for dense retrieval, (c) a rolling conversational summary on the SQLite side so `handle_agent_message` doesn't have to replay 2k messages. Don't adopt Letta — it owns the runtime, which Conexus already owns. Don't adopt Zep unless cross‑session temporal reasoning becomes a product requirement.

---

## 2. Taxonomy

Agent memory papers lean on a cognitive‑architecture analogy (ACT‑R, Soul, CLARION). The mapping isn't rigorous — it's a vocabulary — but it keeps designs honest.

| Type           | Cognitive analogue       | Horizon          | Typical store                       | Conexus today |
|----------------|--------------------------|------------------|-------------------------------------|---------------|
| **Working**    | Working memory / attention | Single turn      | The live context window             | Built into LiteLLM call |
| **Short‑term** | Phonological loop        | Current session  | Recent N messages + rolling summary | SQLite `messages` table, no summary |
| **Episodic**   | Hippocampal episodes     | Timestamped events | Append‑only log + vector index    | SQLite log; no index |
| **Semantic**   | Neocortical facts        | Durable          | KV store / KG / wiki / vector DB    | Markdown wiki (`/data/wiki`) |
| **Procedural** | Skills / motor programs  | Durable          | Code, prompt fragments, tool defs   | `SKILL.md` files |

Two axes cut across all five: **who writes** (the agent itself, a sleep‑time consolidator, or the developer) and **how it's retrieved** (always‑in‑context, explicit tool call, or invisible RAG). A clean framework separates these. Letta mixes agent‑writes with always‑in‑context for core blocks; Mem0 does sleep‑time writes with invisible RAG for retrieval.

---

## 3. Storage substrates

**In‑context (system prompt / appended blocks).** Zero latency, perfect fidelity, but caps your context. Letta "core blocks" live here. For Conexus this is `AgentHandlerConfig.system_prompt` + the BRT time append. Cheap to expand up to ~4–8 KB before cache invalidation starts to hurt.

**SQLite.** What Conexus already uses. Great for message logs, idempotency (`ping_log`), budget state, user prefs. Poor at similarity search. FTS5 gives you BM25 for free — underused in Conexus. Lives on the Fly volume.

**Vector DBs.**
- **Chroma** — simplest Python API, embedded or client/server. Fine for prototypes, gets creaky past a few million vectors.
- **Qdrant** — Rust, HNSW, strongest payload filtering and horizontal scale. Pick if you need filtered search (e.g. "only Leandro's memories from last quarter").
- **pgvector** — Postgres extension. No new service if you already run Postgres; Conexus doesn't, so adding it is adding a database.
- **LanceDB** — embedded, columnar (Lance format), zero‑copy, runs in‑process like SQLite. IVF_PQ indexing. **Best fit for Conexus's "one process on Fly + volume" shape** — no separate server, sits next to `conexus.db` on `/data`.

**Graph DBs (Neo4j, Kùzu, Memgraph).** Required only if relationships between entities matter for reasoning (Graphiti / Zep ride on Neo4j by default, FalkorDB optional). Heavy operational weight for one process on Fly.

**Markdown files.** Human‑readable, git‑versionable, diffable in PRs, editable by Claude Code, renderable in Obsidian. Zero retrieval intelligence on their own — you bolt BM25 + embeddings on top. Conexus's wiki is exactly this pattern.

**Knowledge graphs built ad‑hoc.** Triples (subject, predicate, object) in SQLite + NetworkX often beats running Neo4j for <1M nodes. Mem0g and Graphiti both have "lite" graph modes.

**Hybrid.** The production sweet spot is almost always SQLite (structured) + vector DB (dense) + markdown or JSON documents (payload). Add a graph only when queries like "which facts contradict X" become frequent.

---

## 4. MemGPT / Letta — self‑editing memory

MemGPT (the paper, ~2023) reframed the context window as OS‑style virtual memory. Letta is its production descendant.

**Core blocks.** Labeled sections of the system prompt (`human`, `persona`, custom) that the agent edits via tool calls: `core_memory_append`, `core_memory_replace`. Each block has a character cap (default 2k). Always in context.

**Recall memory.** Full message history in a SQL store; agent queries with `conversation_search` (FTS) and `conversation_search_date`. The agent decides when to scroll back.

**Archival memory.** Vector DB for "things I should remember but that don't fit in core". Agent calls `archival_memory_insert` and `archival_memory_search`. Roughly equivalent to Conexus's wiki but without the human readability.

**The scheduler pattern (2025 "sleep‑time compute").** Instead of the reactive agent doing memory consolidation inline (which costs latency and tokens on the user's dime), a second agent runs asynchronously: reads recent messages, rewrites core blocks, compresses archival entries. This is the single biggest Letta improvement post‑MemGPT paper and the pattern to steal even if you don't adopt Letta itself.

**When to use Letta:** you need stateful agents and don't yet have a runtime. Conexus already has a runtime (`agent_handler.py` + `agent_registry.py`). Adopting Letta means throwing that away. Don't.

---

## 5. Mem0

Mem0 is a *memory service*, not a runtime. You call `mem0.add(messages, user_id=...)` after a turn and `mem0.search(query, user_id=...)` before the next one. It's model‑agnostic and sits alongside whatever agent framework you have — this makes it a much better fit for Conexus than Letta.

**Extraction phase.** An LLM call reads (a) latest exchange, (b) rolling summary, (c) last m messages, and emits atomic facts ("Leandro uses `uv` not pip", "Conexus deploys to `gru`"). Ignores small talk.

**Update phase.** For each new fact, retrieve top‑s similar existing memories, then a second LLM call (function‑call interface) picks one of **ADD / UPDATE / DELETE / NOOP**. This is the clever bit — the conflict resolution is delegated to the same LLM that's reading the memories, via structured output. No vector‑similarity threshold heuristics; just ask the model.

**Storage.** Facts go to a vector DB (Qdrant default) with metadata (user_id, created_at, role). Graph variant **Mem0g** runs a parallel entity extractor + relation generator, producing a labeled directed graph. Mem0g wins on relational questions ("who introduced X to Y?"); flat Mem0 is cheaper and wins on factual recall.

**Reported numbers.** 26% relative accuracy gain over OpenAI's built‑in memory on LOCOMO, 91% lower p95 latency, 90% fewer tokens. Take with a grain of salt — author‑run benchmarks — but the architecture is sound and the code is open source.

**For Conexus:** the extraction + ADD/UPDATE/DELETE loop is what you want to bolt onto the wiki. See §13.

---

## 6. Zep / Graphiti

Zep is a hosted/self‑hosted memory layer. Graphiti is its open‑source engine (`getzep/graphiti` on GitHub, Neo4j or FalkorDB backend). The distinguishing trick: **bitemporal knowledge graph**.

Every node and edge carries two timestamps:
- **t_event** — when the thing actually happened / was true
- **t_ingest** — when Zep learned about it

When a new fact contradicts an old one, Zep doesn't delete the old edge — it marks it `invalidated_at = now()` and writes the new one. This gives you "what did the agent believe about Leandro's job on March 3rd?" for free. It also means temporal reasoning ("has Leandro changed positions this year?") works natively.

Zep reports 94.8% on the Deep Memory Retrieval (DMR) benchmark vs MemGPT's 93.4%, with 90% latency reduction. The graph gives enterprise‑flavoured queries ("which facts about account X were superseded in Q1?") that flat vector stores can't answer.

**Cost:** Neo4j is a whole database to run. Graphiti without Zep is a ~3k‑LOC Python library; it's tractable but it's still a knowledge graph to maintain. For Conexus (one‑user personal agent, <50k memories in 10 years), bitemporal reasoning is overkill. File it under "adopt if Pesquisador starts doing entity‑centric research with many conflicting sources."

---

## 7. Conversation summarisation

You cannot keep raw messages in context forever. Three strategies, in increasing sophistication:

1. **Rolling buffer.** Keep last N tokens verbatim; drop older ones. Simplest, loses everything old. Conexus today.
2. **Rolling summary.** Every K turns, an LLM rewrites the pre‑window history into a paragraph. Keep `summary + last_N_messages` in context. Mem0 uses this as input to its extractor. Straightforward to add: add a `conversation_summary` column on `sessions` in SQLite, refresh on every call past a threshold.
3. **Hierarchical summaries.** Summaries of summaries. LangChain's `ConversationSummaryBufferMemory` and Anthropic's own "memory tool" blog both do a variant. Good for month‑long sessions; unnecessary if your sessions are hours.
4. **Entity tracking.** Maintain `{entity → latest_facts[]}` alongside the summary. Prevents the classic failure mode where the summary says "discussed travel" but forgets *Paris, May 12*. Mem0 and Zep both do this implicitly.

Rule of thumb: if the summary compresses >20× and your recall@k on LOCOMO‑style probes drops below 70%, switch to entity‑tracked summaries.

---

## 8. Markdown / wiki as memory

The "Karpathy LLM wiki" pattern (late 2025) formalised what Conexus was already doing: **the LLM is the librarian, Obsidian is the IDE, the wiki is the codebase.** Instead of RAG over raw documents, the agent incrementally authors a persistent, interlinked markdown knowledge base. Implementations: `wac81/LLM_wiki`, `kytmanov/obsidian-llm-wiki-local`, `Ar9av/obsidian-wiki`, `NicholasSpisak/second-brain`.

**Pros (real, and they apply to Conexus):**
- Human‑readable. Leandro can open `/data/wiki/ana/calendar_notes.md` in Obsidian and read/edit it.
- Versionable. `wiki_store.py` commits on every change → time travel + audit.
- Diffable. You can PR‑review memory changes.
- Tool‑agnostic. Claude Code, Cursor, Conexus agents, and a human all edit the same files.
- Forkable. `git clone` is your export/backup story.

**Cons:**
- No native embedding. Retrieval quality depends on what you bolt on.
- LLM latency for writes. Every memory update is an LLM call that reads‑modifies‑writes a file.
- Conflict surface. Two agents writing the same file concurrently needs a lock or CRDT.
- Scaling. At 10k+ notes, "agent browses the wiki" becomes "agent can't find anything" without retrieval.

**Retrieval on top:** `qmd` (BM25 + vector + LLM rerank via RRF) is the reference implementation; `ripgrep` + embeddings stored next to each file works too. Obsidian's graph view is a free debugging UI.

**BMAD / Continue.dev note:** BMAD‑METHOD agents and Continue.dev both treat `/memories/*.md` or `.continue/rules/*.md` as procedural memory (not semantic). Useful for "how we do things here" — exactly the role of Conexus's `SKILL.md`.

---

## 9. Self‑updating memory — when, who, how

**When to write.**
- After every assistant turn (Letta style): high recall, high cost.
- Batched, async, after the session ends (Mem0 default): cheaper, eventually consistent.
- Only when a tool explicitly commits (Conexus today with `wiki_write`): predictable but puts the burden on the prompt.

**Who validates.** Three models in the wild:
1. *No validation* — trust the LLM, accept drift (LangChain memory, default Mem0).
2. *Self‑reflection* — a second LLM call asks "is this consistent with existing memories?" (A‑MEM, Zep edge invalidation).
3. *Human in the loop* — memory writes surface as diffs (git) that a human can revert. This is what the wiki gives Conexus for free.

**Conflict resolution.**
- **Overwrite** (naive): last write wins. Loses history.
- **Supersede** (Zep bitemporal): old edge marked invalid, new edge added. Best fidelity, most complexity.
- **Merge via LLM** (Mem0 UPDATE): LLM rewrites one memory to incorporate the new fact. Practical middle ground.

**Forgetting / decay.**
- **Hard TTL** on ephemeral facts ("user is currently in Paris" expires in 7 days).
- **Exponential decay on retrieval score** — every access refreshes; unaccessed memories sink. Cheap to implement.
- **LLM‑driven pruning** — sleep‑time agent reviews stale candidates and deletes. Expensive, best quality.

For Conexus: git is your audit log, so aggressive pruning is safe. Start with TTL on known ephemeral fields and an LLM pruning job in `jobs.py` running weekly.

---

## 10. Retrieval strategies

| Strategy       | Works when                       | Cost       | Notes |
|----------------|----------------------------------|------------|-------|
| **BM25 / lexical** | Keywords match exactly (names, IDs) | Near‑zero | SQLite FTS5 gives this for free |
| **Dense / embeddings** | Semantic paraphrase           | 1 embedding/query | Needs a vector index |
| **Hybrid (RRF)** | Mixed corpus, unknown query style | Sum of both | Default in 2025 production RAG |
| **Reranking** (Cohere, bge‑reranker) | You have >20 candidates | 1 rerank call | Biggest single quality lift |
| **Query rewriting** | Short/ambiguous queries      | 1 LLM call | "what did we decide?" → "decisions about X in session Y" |
| **HyDE**       | Query/doc vocabulary gap      | 1 LLM call | Mixed 2025 results — *underperforms* plain dense on numeric/financial. Use only after measuring. |

Production stack (see Hightower 2025): BM25 + pgvector top‑50 → RRF merge → bge‑reranker top‑10 → LLM rubric rerank top‑5. For Conexus's size, skip the last step; stop at cross‑encoder rerank.

---

## 11. Memory evaluation

You cannot improve what you don't measure. Minimum viable eval harness:

- **Recall@k** on seeded facts. Inject 50 facts over 20 sessions, then ask questions whose answer requires those facts. Measure fraction where the correct memory is in the top‑k retrieved.
- **Faithfulness.** Given the retrieved memory, does the final answer actually use it? LLM‑as‑judge with a rubric ("answer is grounded in retrieved context: yes/no/partial").
- **Staleness tests.** Write fact F₁ at t=0, write contradicting F₂ at t=10. At t=20, does the agent return F₂? LOCOMO ignores this; write your own.
- **LOCOMO** — 300 multi‑session dialogues with QA, summarisation, and multimodal tasks. Standard, but Hindsight and Locomo‑Plus have shown it doesn't catch staleness or confidence‑calibration bugs.
- **Cost / latency budget.** Retrieval should stay under ~500ms p95 and ~2k tokens per turn, or you're spending the memory savings on the memory system.

Run these on every change to the memory pipeline, pin baselines, fail CI on regression. The surprising result is usually that the simple BM25 baseline beats your clever thing until you add reranking.

---

## 12. Citations

- **MemGPT** — Packer et al., *MemGPT: Towards LLMs as Operating Systems*, arXiv:2310.08560 (2023).
- **Letta** — `github.com/letta-ai/letta`; docs at `docs.letta.com/concepts/memgpt/` and `docs.letta.com/advanced/memory-management/`.
- **Mem0** — Chhikara et al., *Mem0: Building Production‑Ready AI Agents with Scalable Long‑Term Memory*, arXiv:2504.19413 (2025). Repo `github.com/mem0ai/mem0`.
- **Zep / Graphiti** — Rasmussen et al., *Zep: A Temporal Knowledge Graph Architecture for Agent Memory*, arXiv:2501.13956 (2025). Repo `github.com/getzep/graphiti`.
- **A‑MEM** — Xu et al., *A‑Mem: Agentic Memory for LLM Agents*, arXiv:2502.12110 (NeurIPS 2025). Repo `github.com/agiresearch/A-mem`.
- **LOCOMO** — Maharana et al., *Evaluating Very Long‑Term Conversational Memory of LLM Agents*, ACL 2024; `snap-research.github.io/locomo`.
- **HyDE** — Gao et al., *Precise Zero‑Shot Dense Retrieval without Relevance Labels*, arXiv:2212.10496.
- **Karpathy LLM‑wiki pattern** — `github.com/wac81/LLM_wiki`, `github.com/tjiahen/awesome-llm-wiki`.
- **Hybrid retrieval reference** — Hightower, *Stop the Hallucinations: Hybrid Retrieval with BM25, pgvector, embedding rerank, LLM Rubric Rerank & HyDE* (2025).

---

## 13. Conexus‑specific recommendation

**Phase 9 additions to the SQLite layer (shipped 2026-05-01):**

`SqliteStore.init_db()` now calls `init_tool_audit(conn)` in addition to `init_handoff_audit(conn)`, creating the `tool_audit` table on first boot (`src/conexus/core/memory/sqlite_store.py:127`).

`SqliteStore.conn` (property, `src/conexus/core/memory/sqlite_store.py:137`) opens a direct, unclosed `sqlite3.Connection`. Caller is responsible for `.close()`. Intended for long-lived operations — `handle_team_message` uses it to hold a single connection across the full team session rather than opening per-write connections.

`tool_audit` table (see `src/conexus/core/memory/tool_audit.py`) — per-tool-call record for replay fidelity: `(id, ts, session_id, agent, tool, args_json, result, outcome)`. Indexed on `session_id`. Populated by `record_tool_call(conn, *, session_id, agent, tool, args, result, outcome)`.

**Phase 10 additions — agent identity baseline (shipped 2026-05-03):**

**`facts` table — v1→v2 migration (agent-scoped).** The table primary key is now `(agent_id, key)` instead of a bare `key` (`src/conexus/core/memory/sqlite_store.py:12`). All fact methods gained a mandatory first argument `agent_id: str` (`fact_get`, `fact_set`, `facts_list`, `facts_recent`, `fact_delete` — lines 159–202). On first `init_db()` call against an old DB, `_migrate_facts_v1_to_v2()` renames the legacy table and re-inserts rows under `agent_id='_legacy'` (`src/conexus/core/memory/sqlite_store.py:99`). Cross-agent isolation is now native.

**`identity_blocks` table** (`src/conexus/core/memory/sqlite_store.py:74`). Schema: `(agent_id, name, content, budget_chars, updated_at)`, PK `(agent_id, name)`. Accessed exclusively via `BlockStore` (`src/conexus/core/identity/blocks.py`). `BlockStore.set(agent_id, name, content, budget_chars)` raises `BlockOverBudgetError` when `len(content) > budget_chars`. Blocks are char-budgeted mutable text buffers (Letta-style core memory) that agents can update via `block_set` tool calls. Budget chars are declared in `SKILL.md identity.blocks`.

**`chat_summaries` table** (`src/conexus/core/memory/sqlite_store.py:83`). Schema: `(agent_name, chat_id, summary_text, covers_until_msg_id, token_count, updated_at)`, PK `(agent_name, chat_id)`. Populated by `HistoryCompactor` (`src/conexus/core/history/compactor.py`). New store methods: `summary_get(agent_name, chat_id) -> dict | None` (line 257), `summary_set(...)` (line 266), `chat_after(agent_name, chat_id, after_msg_id) -> list[dict]` (line 288 — `chat_id` param accepted but ignored since `chat_history` has no `chat_id` column; all history for an agent is one logical chat).

**`HistoryCompactor`** (`src/conexus/core/history/compactor.py`). Replaces the plain `chat_recent(limit=10)` call when `history_cfg + summarize_fn` are both set in `AgentHandlerConfig`. Algorithm: (1) load existing summary; (2) fetch messages after `covers_until_msg_id`; (3) pin last `keep_verbatim` turns; (4) greedily fill budget with older turns newest-first; (5) if leftover messages exist and usage ≥ `trigger_pct`, call `summarize_fn(old_summary, leftover)` and persist. Compaction stores the new summary back via `summary_set`. The `summarize_fn` factory is `make_summarizer(llm_call, budget_tokens)` in `src/conexus/core/history/summarizer.py` — emits a pt-BR prompt that updates a rolling summary while respecting a token budget. The legacy `chat_recent(limit=10)` path is preserved when neither `history_cfg` nor `summarize_fn` is set (backward compatible).

**Identity context assembly.** `assemble_identity_context(agent_id, cfg, store, wiki, blocks, skill_dir=None) -> str` (`src/conexus/core/identity/context.py`) produces a markdown string injected at the front of the system prompt when `cfg.enabled`. Output sections in order: (0) memory-routing prompt (`load_memory_prompt(cfg.prompt_override, skill_dir)` — `src/conexus/core/identity/prompt.py:29`), then `## Block: <name>` for each declared block with content, `## Fatos recentes` when `facts.inject_recent > 0`, `## Wiki (índice)` when `wiki.inject_index is True`. Empty sections are omitted. `handle_agent_message` calls `assemble_identity_context` with `ir.skill_dir` and prepends the result before `cfg.system_prompt` (`src/conexus/core/agent_handler.py:116–123`). Legacy `include_facts` injection is suppressed when identity is active to prevent double-injection.

**`IdentityTools`** (`src/conexus/core/identity/tools.py`). Built-in tool class auto-registered as a second backend when identity is active. Exposes: `memory_get/set/list_facts/delete`, `block_get/set/list`, `wiki_read/list/search/write/append_log`. All methods are scoped to `agent_id` passed at construction. `block_set` validates that `name` is declared in `identity.blocks`; returns `{"ok": False, "error": ...}` on budget overflow (does not raise to the LLM).

**`IdentityRuntime`** (`src/conexus/cli/identity_runtime.py`). Holds `agent_id`, `cfg` (IdentitySection), `store`, `skill_dir` (public `Path` attribute — line 26), `blocks` (BlockStore), `wiki` (WikiStore | None), `tools` (IdentityTools). Wiki is built via `_build_wiki(cfg.wiki, skill_dir, agent_id=agent_id, store=store)` (line 30) which dispatches on `wiki_cfg.backend`: `"local"` → `WikiStore.local(path)`, `"github_app"` → reads install row from `store.github_app_install_get(agent_id)` and builds `GitHubAppBackend` (Phase 2, shipped 2026-05-08). Constructed by `build_identity_runtime(agent_id, cfg, store, skill_dir)` — returns `None` when `cfg` is None or `cfg.enabled` is False. Seeds `initial` block content on first run. `build_runtime` in `src/conexus/cli/runner.py` creates the runtime and stores it in `AgentRuntime.identity`. `__main__.py` registers `runtime.identity.tools` as a second `PythonBackend` in the registry when non-None (`src/conexus/cli/__main__.py:82–84`).

**Keep:**
- `core/memory/sqlite_store.py` — episodic log, idempotency, budget state, tool + handoff audit, facts, blocks, summaries, GitHub App installs.
- `core/memory/wiki_store.py` — semantic memory facade. Phase 1 ships `LocalBackend`; Phase 2 ships `GitHubAppBackend` (both live — see Phase 2 additions below). The facade API is stable: `read/write/list/search/delete` + `append_log`/`update_index` conveniences (`src/conexus/core/memory/wiki_store.py`). Per-agent wiki dirs live at `agents/<name>/wiki/` (excluded from git via `.gitignore`).
- `core/memory/wiki/backend.py` — `WikiBackend` Protocol (`@runtime_checkable`). Six methods: `read/write/list/search/exists/delete`. `safe_join(root, relpath)` path-safety helper rejects `..`, absolute paths, backslashes, and symlink escapes.
- `core/memory/wiki/local.py` — `LocalBackend` impl: plain directory, no auth/network/git. Auto-creates root on construction. All ops guarded by `safe_join`.
- `SKILL.md` files — procedural memory; perfect as is.

**Phase 1 additions — memory-and-wiki architecture (shipped 2026-05-08):**

**`WikiBackend` Protocol + `LocalBackend`.** New package `src/conexus/core/memory/wiki/` introduces a pluggable storage layer. `WikiBackend` (`backend.py:8`) is a `@runtime_checkable` Protocol with six methods. `LocalBackend` (`local.py:9`) is the default impl — plain filesystem under a resolved root. `WikiStore` is now a thin facade: `__init__` accepts `WikiBackend | str | Path`; passing a path or string is the back-compat shim that builds a `LocalBackend` internally (`wiki_store.py:16–21`). `WikiStore.local(root)` classmethod is the preferred constructor.

**`WikiSection.backend` field.** `src/conexus/core/config/skill_loader.py:53–64`. `WikiSection` gained `backend: str = "local"` with a validator rejecting anything outside `{"local", "github_app"}`. `repo: str | None = None` is a Phase 2 stub. `IdentitySection.wiki` now defaults to `Field(default_factory=WikiSection)` (line 81) so agents without an explicit `wiki:` block still get a local wiki — previously defaulted to `None`.

**`IdentitySection.prompt_override` field.** `src/conexus/core/config/skill_loader.py:83`. Optional path to a custom memory-routing prompt file. Resolved relative to `skill_dir` by `load_memory_prompt`.

**Default pt-BR memory-routing prompt.** `src/conexus/core/identity/prompt.py`. `DEFAULT_MEMORY_PROMPT_PT_BR` (line 10) is a 3-tier guidance block explaining when to use `memory_set` (atomic identity facts), `wiki_write` (narrative content), and `add_note` (ephemeral lists). Auto-prepended as the first section of `assemble_identity_context` for every identity-enabled agent. Override with `identity.prompt_override: ./custom.md` in SKILL.md.

**`notes` pack tool descriptions tightened.** `packs/notes/tools.py:15–30`. `add_note` description now warns against using it for personal identity facts and redirects to `memory_set`/`wiki_write`. This guides the LLM to the correct store on first try without needing extra prompt text.

**Phase 2 additions — GitHubAppBackend (shipped 2026-05-08):**

**`github_app_installs` table** (`src/conexus/core/memory/sqlite_store.py:118`). Schema: `(agent_id TEXT PK, repo_slug TEXT, installation_id INTEGER, created_at TEXT)`. Store helpers: `github_app_install_set(agent_id, repo_slug, installation_id)` — upsert on conflict; `github_app_install_get(agent_id) -> dict | None`; `github_app_install_delete(agent_id)` (`sqlite_store.py:398–427`). One row per agent; installing a new repo overwrites the previous row.

**`git_auth.py`** (`src/conexus/core/memory/wiki/git_auth.py`). Two functions: `_make_jwt(app_id, private_key_pem) -> str` — signs a 9-minute JWT using PyJWT + RS256 (`iat = now - 60`, `exp = now + 540`); `get_installation_token(app_id, private_key_pem, installation_id) -> str` — module-level `_TOKEN_CACHE: dict[int, tuple[str, float]]` keyed by `installation_id`, evicts 5 minutes before expiry (`time.time() < expires - 300`). On miss, calls `POST https://api.github.com/app/installations/{id}/access_tokens` via `httpx` (sync, 10 s timeout).

**`GitHubAppBackend`** (`src/conexus/core/memory/wiki/github_app.py`). Implements `WikiBackend` Protocol. Composes `LocalBackend` for all file operations. Git subprocess calls are synchronous (blocks the asyncio event loop — MVP acceptable; `asyncio.to_thread` deferred). Key internal methods: `_ensure_clone()` — if `.git/` absent, `git clone`; on empty-repo clone failure, `git init` + `git remote add origin`; sets `user.name = Conexus`, `user.email = noreply@conexus.ai`; `_refresh_remote()` — `git remote set-url origin <token-URL>` (called before every network op to rotate the short-lived token); `_pull()` — `_refresh_remote()` then `git pull --ff-only origin main` (non-fatal on failure); `_commit_push(message)` — `git add -A`, checks `git diff --cached --quiet` (no-ops if nothing staged), then `git commit -m message` + `_refresh_remote()` + `git push origin main`. Per-method behaviour: `read/list/search` pull before delegating to `LocalBackend`; `write` pulls, writes locally, then commits+pushes; `delete` pulls, deletes locally (raises `FileNotFoundError` if missing), then commits+pushes; `exists` delegates directly (no pull — local-only check).

**`_build_wiki` dispatch** (`src/conexus/cli/identity_runtime.py:45`). Signature changed to `_build_wiki(wiki_cfg, skill_dir, *, agent_id="", store=None)`. The `github_app` branch reads `store.github_app_install_get(agent_id)`; raises `RuntimeError` if no install row exists (directing the operator to Studio); reads `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY` from env; constructs `GitHubAppBackend(local_root=skill_dir/"wiki", ...)` and wraps it in `WikiStore`. Tech debt: `local_root=skill_dir/"wiki"` may need to move to `data_dir/"wiki"` for Fly.io volume persistence across deploys.

**`make_github_wiki_router(store)`** (`src/conexus/web/admin/routes/github_wiki.py`). `APIRouter(prefix="/admin/oauth/github")`. Two endpoints: `GET /start?agent=&repo=` — writes `(nonce, "gh:{agent}:{repo}")` into `oauth_pkce_state.code_verifier` (the `gh:` prefix isolates from Phase 11 PKCE rows), reads `GITHUB_APP_SLUG` from env, redirects to `https://github.com/apps/{slug}/installations/new?state={nonce}`; `GET /callback?installation_id=&state=` — validates nonce exists and `code_verifier` starts with `gh:`, extracts `agent` + `repo_slug`, deletes the nonce row, calls `store.github_app_install_set(...)`, redirects to `/admin/agents/{agent}`. Router is registered in `make_admin_app` via `app.include_router(make_github_wiki_router(_store))` (`web/admin/app.py:65`), where `_store` is initialised with the Studio `data_dir` DB.

**Add (ranked by ROI):**
1. ~~**Rolling conversational summary** in SQLite.~~ **Done in Phase 10** — `HistoryCompactor` + `chat_summaries` table.
2. **Mem0‑style extractor** writing into the wiki. After each session, a cheap LLM reads the transcript + current relevant wiki pages and emits ADD/UPDATE/DELETE ops as `wiki_write` / `wiki_delete` calls. Existing tools, new orchestrator job in `jobs.py`. Git gives you audit + rollback for free.
3. **LanceDB index over the wiki.** Embedded, lives on `/data` next to `conexus.db`, no new service. Populate on `wiki_write`, query via a new `wiki_search_semantic` tool. Keep the existing text grep tool — hybrid beats either alone.
4. **Cross‑encoder rerank** (bge‑reranker‑base via HF inference API or local) on combined BM25+dense results. Biggest quality jump per LOC.
5. **Memory eval harness** under `tests/memory_eval/`. Seed facts, probe questions, run in CI. Pin baselines.

**Skip:**
- **Letta** — it owns the runtime; Conexus already has one.
- **Zep / Graphiti** — bitemporal KG is overkill for a single‑user agent until Pesquisador starts doing contradictory‑source research.
- **Pinecone / managed vector DBs** — violates the "one process + one volume" deployment shape.
- **HyDE** — only after measuring, and only if query/document vocabulary actually diverges.

**Sleep‑time consolidation** is the pattern to steal from Letta regardless of adoption: the reactive path stays cheap; a nightly APScheduler job re‑reads the day's transcripts and consolidates. That already fits Conexus's scheduler architecture perfectly.
