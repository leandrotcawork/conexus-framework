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

**Keep:**
- `core/memory/sqlite_store.py` — episodic log, idempotency, budget state.
- `core/memory/wiki_store.py` — semantic memory. Git‑backed markdown is the *strongest* piece of Conexus's memory stack; don't replace it.
- `SKILL.md` files — procedural memory; perfect as is.

**Add (ranked by ROI):**
1. **Rolling conversational summary** in SQLite. One new column (`sessions.summary`), refreshed every ~20 turns. Unblocks long sessions without context bloat. <100 LOC.
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
