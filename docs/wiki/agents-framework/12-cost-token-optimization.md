# 12 — Cost & Token Optimization for LLM Agents

> Operator reference for Conexus. Numbers are April 2026 list prices (USD per 1M tokens) unless stated. Conexus routes every call through LiteLLM (`core/llm/`) and enforces per-agent `BudgetCap` via `CapChecker`, so every technique here is either a router config change, a prompt-shape change, or an accounting hook.

---

## 1. Executive summary

An agent's bill is driven by four multiplicative factors: **tokens per turn × turns per task × model $/token × cache miss rate**. Optimizing one without the others is wasted effort. For a 24/7 Telegram agent like Ana or Pesquisador, the realistic wins stack like this:

| Lever | Typical saving | Conexus surface |
|------|---------------|-----------------|
| Prompt caching (stable system prompt + tools) | 70–90% on input | `handle_agent_message` prompt ordering |
| Cheap-model-first routing (Flash → Pro cascade) | 5–10× | LiteLLM router + `llm_synthesis` split |
| Tool-result truncation / pagination | 40–70% | `core/tools/` + `AgentRegistry.execute_tool` |
| Batch API for non-interactive jobs | 50% flat | scheduled `jobs.py` work |
| Command output filtering (RTK-class) | 60–90% on terminal tools | pesquisador shell tools |
| Budget cap + observability | prevents runaway | `core/budget/`, `UsageTracker` |

A well-tuned reactive turn on Gemini 2.5 Flash with caching lands near **$0.0003–0.001**. An unoptimized Pro turn with a 30k-token uncached context and verbose tool output lands near **$0.05–0.15** — a 100–500× spread. That spread is the entire problem.

---

## 2. Where tokens go

Account for every token class before optimizing:

1. **System prompt / persona.** Conexus loads `SKILL.md` body once per turn. For Ana this is ~1.5–3k tokens. Stable → cache it.
2. **Tool schemas.** `core/tools/schema_gen.py` emits one JSON schema per tool method. Each tool costs 80–300 tokens; a 10-tool agent spends ~1.5–3k tokens per turn on schemas alone. Stable → cache it.
3. **Memory / wiki context.** `WikiStore` retrievals, `SqliteStore` recent turns, calendar snapshots. Can balloon to 5–20k tokens. Cache partially; prune aggressively.
4. **Conversation history.** Grows linearly until pruned. Biggest silent cost in long sessions.
5. **Tool results.** Raw command output, HTTP responses, Google Calendar JSON — often the single largest input class. 50k-token `curl` dumps are not hypothetical.
6. **Reasoning / thinking tokens.** Claude extended thinking and Gemini 2.5 thinking are billed as output. A Gemini 2.5 Pro "thinking" turn can emit 2–8k invisible output tokens before the visible answer.
7. **Output.** Usually the smallest class. Don't over-optimize here at the expense of quality.

Rule of thumb: if you can't name which of these seven dominates your agent's bill, instrument before tuning.

---

## 3. Prompt caching

The highest-leverage lever. All three providers now implement caching, with different semantics.

### Anthropic (explicit)

- **Breakpoints:** up to 4 `cache_control` markers per request. Everything *before* a breakpoint becomes a cacheable prefix.
- **TTL:** 5 minutes default; 1 hour optional. In early March 2026 Anthropic silently regressed the default from 1h → 5m, inflating bills for agents that assumed 1h — check your cache-hit metrics.
- **Pricing (Claude 3.7 Sonnet class):** cache **write** = 1.25× input (5m) or 2× input (1h). Cache **read** = 0.1× input. Breakeven = 1 hit (5m) or 2 hits (1h).
- **Cache rules:** prefix match from token 0. Any change to earlier content invalidates everything after. Minimum cacheable block ~1024 tokens (Sonnet/Opus).

### OpenAI (implicit, automatic)

- Zero configuration. Cached input tokens are billed at **50% off** (GPT-5 class) once a prefix has been seen within the last ~5–10 minutes.
- Minimum 1024 cached tokens, growing in 128-token increments.
- **Stacks with Batch API**: combined 50% batch × 50% cache ≈ 75% off on cached portions.

### Gemini (context caching, explicit)

- Create a `CachedContent` object; attach to calls via `cached_content=...`.
- Cached reads: **25% of base input**. Storage: **$1.00/M tokens/hour** (Flash) to **$4.50/M tokens/hour** (Pro).
- Breakeven depends on hit rate and TTL — long-lived caches for rarely-hit content lose money on storage.

### Cache-aware prompt ordering (MANDATORY for Conexus)

Order prompt sections most-stable → most-volatile so the cacheable prefix is maximized:

```
[1] System persona (SKILL.md body)     ← stable across weeks
[2] Tool schemas (schema_gen output)   ← stable across deploys
[3] Long-term memory / wiki refs       ← stable per session
[4] Conversation history (older)       ← append-only, mostly stable
[5] Latest user turn + tool results    ← volatile
```

In `handle_agent_message`, the current BRT timestamp goes at the **end** of the system prompt, not the beginning — otherwise every single call invalidates the whole cache. This is already the convention; do not break it.

---

## 4. Context compression

When caching isn't enough (long-running Pesquisador research loops, multi-day Ana conversations):

- **Summarisation checkpoints.** Every N turns, replace the middle of the conversation with a model-generated summary. Cheap model (Flash) is fine for the summarizer.
- **Pruning by salience.** Drop tool results older than K turns unless referenced. Keep their IDs so the agent can re-fetch.
- **Sliding window.** Hard cap turns-in-context. Simple; works when tasks are short.
- **Semantic dedup.** For wiki/RAG results, embed and drop near-duplicates before injection. Cuts 20–40% on retrieval-heavy agents.
- **LLMLingua / LLMLingua-2.** Microsoft's perplexity-based prompt compressor, up to 20× ratio with ~1.5% loss on GSM8K. LLMLingua-2 is 3–6× faster than LLMLingua-1, integrates with LangChain/LlamaIndex. Reasonable fit for static document context; *not* for tool schemas (lossy on JSON) or system prompts (breaks tone).
- **Context distillation.** Offline: ask a big model to rewrite a verbose reference into a compact one, ship the compact version. Works well for `SKILL.md` personas and operator manuals.

Conexus integration point: add a `core/memory/compressor.py` that wraps the conversation slice handed to `handle_agent_message`, with a per-agent policy.

---

## 5. Model routing

A single model for every task is the most expensive mistake.

### Cheap-model-first / cascade

1. Route to Gemini 2.5 Flash ($0.30 in / $2.50 out per M).
2. If the response fails a validator (JSON schema, confidence score, "I don't know" regex), **escalate** to Gemini 2.5 Pro ($1.25 in / $10 out per M) or Claude Sonnet.
3. Return escalated answer; log the escalation for offline tuning.

Pesquisador already embodies this pattern — cheap router (`llm:`) for tool-calling, Pro (`llm_synthesis:`) for `compile_article`. Generalize it.

### Confidence-based escalation

Ask the cheap model to self-report a confidence score in structured output. Escalate when < threshold. Cheap; surprisingly effective on factual QA.

### LiteLLM router config

```yaml
model_list:
  - model_name: fast
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
    model_info:
      base_model: gemini-2.5-flash   # REQUIRED for accurate cost tracking
  - model_name: smart
    litellm_params:
      model: gemini/gemini-2.5-pro

router_settings:
  fallbacks: [{"fast": ["smart"]}]
  context_window_fallbacks: [{"fast": ["smart"]}]   # auto-escalate on context overflow
  content_policy_fallbacks: [{"fast": ["smart"]}]
```

Always set `model_info.base_model` — Azure and OpenRouter return generic names, which breaks LiteLLM's cost calculator silently.

### OpenRouter

Useful for spot-price routing across providers and for models not directly offered (Llama 3.3 70B, DeepSeek, Qwen). Adds 5% margin but you get failover across clouds for free. Configure as another `litellm_params.model: openrouter/...` entry.

---

## 6. Batch API

- **OpenAI, Anthropic, Gemini** all offer flat **50% off** input *and* output for async batch jobs. SLA: within 24h (usually < 1h for small batches).
- Stacks with prompt caching at OpenAI and Gemini. Not yet at Anthropic (batch excludes cache discounts as of April 2026 — verify before relying on it).
- **Fit for Conexus:** scheduled `jobs.py` work. Nightly digest generation, wiki re-summarisation, weekly analytics — none of these need sub-second latency. Move them to batch and you halve a quarter of the bill.
- **Poor fit:** Telegram reactive turns. User is waiting; batch latency is unacceptable.

Implementation: add a `use_batch: bool` flag on `JobSpec` in `core/scheduler/`. When true, the job writes to a batch queue processed on a 15-minute tick instead of calling LiteLLM synchronously.

---

## 7. Small / local models

- **Gemini 2.5 Flash** — $0.30 in / $2.50 out. Default for almost every Conexus tool call. Beats GPT-4o on tool-calling for 1/10th the cost.
- **Claude Haiku 3.5** — ~$0.80 in / $4 out. Better prose than Flash, still cheap. Good for Ana's brief Portuguese replies.
- **GPT-4.1-mini / GPT-5-nano** — ~$0.40 in / $1.60 out. Strong JSON reliability.
- **Llama 3.3 70B via Groq/Together** — ~$0.59 in / $0.79 out. Fastest per-token throughput on the market. Quality plateau below Pro-class.
- **Quantised local (Llama 3.3 70B Q4, Qwen 2.5 32B Q5) on a 24GB GPU** — marginal cost ≈ electricity. Latency 20–80 tok/s. Fits classification, summarisation, embedding-as-feature — *not* agentic tool-calling (tool-calling quality degrades fast under 4-bit).

Heuristic: if the task is *"classify / extract / summarize"*, you can almost always drop two tiers. If it's *"plan / tool-call / write prose for a user"*, stay on Pro-class.

---

## 8. Tool output hygiene

Tool results are the #1 silent budget killer. Enforce these rules in `core/tools/`:

- **Truncate with intent.** Cap every tool result at N tokens (Conexus default: 4k). Return a tail marker `[… truncated, 37 more lines; call with offset=40 to continue]` so the model knows more exists.
- **Paginate.** `offset` / `limit` params on any list-returning tool. Never return 500 calendar events; return 20 with a cursor.
- **Lazy resources.** Instead of dumping a file, return `{file_id, summary, size_lines}`. Let the model call `read(file_id, lines=10..40)` only if needed.
- **Structured summaries.** Convert JSON-heavy payloads (Google Calendar, API responses) to compact markdown. `AgentRegistry.execute_tool` already JSON-serialises — wrap tool methods so they return pre-summarised dicts, not raw provider blobs.
- **Error hygiene.** Return `{"error": "rate_limited", "retry_after": 30}`, not a 2k-token stack trace.

---

## 9. Batch and parallel tool calls

Both Anthropic and OpenAI support **parallel tool calls** in a single response. Claude 3.5+ and GPT-4.1+ emit multiple `tool_use` blocks per turn; process them concurrently in `handle_agent_message` (it already does via `asyncio.gather`) and return all results in one follow-up message. Each parallel call saves one full round-trip of system-prompt + schema tokens.

**Tool-call batching** at the tool layer: when the agent repeatedly calls `wiki_read(slug)` for 5 slugs, expose a `wiki_read_many(slugs: list[str])` variant. One call, one result, ~80% fewer tokens on schemas and framing.

---

## 10. Streaming and early termination

- **Stream** for user-facing replies — perceived latency drops even though total tokens are unchanged. LiteLLM supports `stream=True` transparently.
- **`stop_sequences` / `stop`** — hard stop generation on sentinel tokens (`"</answer>"`, `"---END---"`). Saves output tokens on verbose models.
- **`max_tokens`** — set per-call, not globally. A classifier tool needs 20 tokens, not 4096.
- **Early-exit validators** — when streaming, run a validator on partial output and abort the stream if structure is clearly broken. Saves the rest of the completion.

---

## 11. Observability + budgets

You cannot optimize what you do not measure. Conexus already has the scaffolding:

- **`UsageTracker`** logs `(agent, model, input_tokens, output_tokens, cached_tokens, cost_usd)` per call.
- **`BudgetCap` + `CapChecker`** enforces per-agent caps before reactive turns (`on_exceed: notify` sends Telegram alert and blocks the call; jobs bypass by design).

Extend this stack with:

1. **Per-tool cost attribution.** Tag each LLM call with the tool context that triggered it. Surfaces expensive tool loops (e.g. Pesquisador ping-ponging between `search` and `wiki_read`).
2. **Per-conversation rollup.** Persist cumulative cost per `chat_id` × day. Makes "why was yesterday $4 and today $40" a one-query answer.
3. **Soft caps with alerts.** At 50% / 80% / 100% of daily cap, post to a monitoring channel. `notify` semantics for 100%, silent for lower tiers.
4. **Cache-hit metric.** Log `cached_tokens / input_tokens` per call. If this drops below ~0.6 for a stable agent, your prompt ordering regressed.
5. **Cost velocity.** $/minute over the last 10 min. Spiking velocity = infinite loop; hard-kill the agent before the bill explodes.

---

## 12. Token killers (RTK and friends)

When an agent shells out to CLI tools (git, grep, docker, curl), raw output is catastrophic. **RTK (Rust Token Killer)** is the current state-of-the-art: a single Rust binary that proxies common dev commands and filters output.

- Typical savings: **60–90%** on `git status`, `git log`, `git diff`, `cargo build`, `pytest`, `npm install`, `grep`, `find`, `ls`, `curl`.
- Usage pattern: prefix every shell invocation with `rtk`. `rtk git status` instead of `git status`. Passthrough for unknown commands, so always safe.
- Claude Code-style tricks that transfer to any agent:
  - Group-by-file for lint output (grouped clippy/ESLint saves ~80%).
  - Failures-only for test output (vitest/pytest savings ~99%).
  - Deduplicated log tails with repeat counters.
  - Route tool results through a `summary` filter before injection.
- MCP bridge `rtk-mcp` exists if you want to expose RTK as structured tool calls instead of shell invocations.

For Conexus: Pesquisador's shell/curl tools should route through RTK when available. Add a thin wrapper in `core/tools/shell.py` that prefixes `rtk` when the binary is on `PATH`, falls through otherwise. Zero behavioural change, 70%+ savings on terminal-heavy research runs.

Adjacent ideas worth stealing:
- **Diff-based context refresh.** Instead of re-sending a full document every turn, send only the diff since last turn. Requires stable anchors.
- **"Caveman mode" stylistic compression.** Prompt the model to reply in ultra-compact telegraphic prose for intermediate reasoning steps, full prose only for the final user-facing answer. 30–50% output savings on long chains.

---

## 13. Citations

### Pricing & caching mechanics
- [Anthropic — Prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Anthropic — Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [GitHub issue: Cache TTL regressed from 1h to 5m, March 2026](https://github.com/anthropics/claude-code/issues/46829)
- [The Register — Claude quota drain postmortem, April 2026](https://www.theregister.com/2026/04/13/claude_code_cache_confusion/)
- [OpenAI — Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
- [OpenAI — Prompt Caching 201 cookbook](https://developers.openai.com/cookbook/examples/prompt_caching_201)
- [Google — Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Google — Vertex AI pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)
- [TokenMix — Prompt caching guide 2026 (cross-provider)](https://tokenmix.ai/blog/prompt-caching-guide)
- [TokenMix — OpenAI Batch API pricing 2026](https://tokenmix.ai/blog/openai-batch-api-pricing)
- [Finout — Anthropic API pricing 2026](https://www.finout.io/blog/anthropic-api-pricing)

### Routing & infrastructure
- [LiteLLM — Router & load balancing](https://docs.litellm.ai/docs/routing)
- [LiteLLM — Fallbacks and retries](https://docs.litellm.ai/docs/proxy/reliability)
- [LiteLLM — Fallback management endpoints](https://docs.litellm.ai/docs/proxy/fallback_management)
- [LiteLLM GitHub](https://github.com/BerriAI/litellm)

### Compression research
- [LLMLingua project page](https://www.llmlingua.com/)
- [LLMLingua-2 paper (arXiv 2403.12968)](https://arxiv.org/abs/2403.12968)
- [LongLLMLingua paper (arXiv 2310.06839)](https://arxiv.org/abs/2310.06839)
- [Microsoft/LLMLingua on GitHub](https://github.com/microsoft/LLMLingua)

### Token killers
- [rtk-ai/rtk GitHub](https://github.com/rtk-ai/rtk)
- [rtk — official site](https://www.rtk-ai.app/)
- [rtk-mcp bridge (MCP server wrapper)](https://github.com/ousamabenyounes/rtk-mcp)
- [RTK architecture — how it works](https://www.mintlify.com/rtk-ai/rtk/concepts/how-it-works)
