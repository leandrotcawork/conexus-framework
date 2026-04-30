# 09 — Observability, Evals, and Guardrails for LLM Agents

> Audience: a senior engineer (and Claude) working on **Conexus**, a Python agent
> framework with multiple agents sharing one runtime. Conexus already has a basic
> `UsageTracker` for per-call cost. It has **no tracing, no evals, no guardrails
> layer**. This doc is the reference for adding those capabilities without
> building everything from scratch.

---

## 1. Executive summary

An LLM agent is a distributed system pretending to be one function call. A single
user message becomes: N LLM calls, M tool calls, possibly a handoff to another
agent, plus retries, caching, and budget checks. When something goes wrong — a
wrong answer, a runaway loop, a $40 bill — you cannot debug it from logs alone.

Three layers are needed:

1. **Observability** — structured traces + metrics for every span (LLM call,
   tool call, agent turn, handoff). Built on **OpenTelemetry GenAI semantic
   conventions** so any backend works.
2. **Evals** — offline datasets + scoring (deterministic asserts, LLM-as-judge,
   RAG metrics) run in CI as regression suites, plus online sampling in prod.
3. **Guardrails** — input classifiers, output validators, and runtime policy
   checks. Independent of the model. Composable with the agent loop.

For Conexus specifically: adopt **OpenTelemetry GenAI** at the `TrackedLLM` and
`AgentRegistry.execute_tool` boundaries, send traces to **self-hosted Langfuse**
(runs in Docker, MIT-licensed, fits the Fly.io profile), wire **promptfoo +
DeepEval** for CI eval suites, and layer **Guardrails-AI** validators around
tool I/O. Keep the existing `UsageTracker`/`CapChecker` as the enforcement path;
add the tracing layer beside it, not instead of it.

---

## 2. What to trace

A trace is a tree of **spans**. For an agent, the canonical shape is:

```
agent.turn (root)                      # one user message -> one final reply
├── budget.check                       # CapChecker.allow()
├── llm.chat                           # TrackedLLM.complete() - iteration 1
│   ├── input: messages (redacted)
│   ├── output: assistant msg + tool_calls
│   ├── tokens: prompt / completion / cache_read / cache_write
│   ├── cost_usd, latency_ms, model, provider
│   └── retry.attempt=1 (if retried)
├── tool.call name=wiki_search         # AgentRegistry.execute_tool
│   ├── input: args (redacted if PII)
│   ├── output: JSON result (truncated)
│   └── latency_ms, status
├── tool.call name=compile_article
│   └── llm.chat (synthesis)           # nested Gemini Pro call
├── llm.chat (iteration 2)             # tool-calling loop continues
└── agent.handoff target=pesquisador   # only when crossing agent boundaries
```

**Minimum fields every span must carry** (per OTel GenAI conventions, see §3):

| Field | Applies to | Notes |
|-------|-----------|-------|
| `gen_ai.system` | LLM | `anthropic`, `google`, `openai` |
| `gen_ai.request.model` / `response.model` | LLM | Useful when router swaps |
| `gen_ai.operation.name` | LLM / agent | `chat`, `embeddings`, `invoke_agent` |
| `gen_ai.usage.input_tokens` / `output_tokens` | LLM | Plus cache tokens |
| `gen_ai.request.temperature`, `top_p`, `max_tokens` | LLM | For repro |
| `gen_ai.tool.name` / `gen_ai.tool.call.id` | tool | Correlate to LLM call |
| `conexus.agent.name` | all | `ana`, `pesquisador` — custom attr |
| `conexus.chat_id` | all | Telegram chat; trace correlation key |
| `conexus.cost_usd` | LLM | Mirror of `UsageTracker` value |
| `conexus.retry.count` | LLM | Budget exhaustion vs transient errors |
| status / error | all | `StatusCode.ERROR` + exception event |

**Inputs/outputs**: OTel recommends putting prompts and completions on span
**events** (not attributes) because of size. Make it a config flag — on in dev,
sampled in prod.

---

## 3. OpenTelemetry for LLMs

The OTel **GenAI SIG** (April 2024–present) publishes semantic conventions that
unify span/attribute names across providers. As of early 2026 most of it is
still "experimental" but already adopted by every serious vendor.

The specs that matter:

- [`gen-ai/gen-ai-spans`](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) — client spans (`chat`, `embeddings`, `generate_content`).
- [`gen-ai/gen-ai-agent-spans`](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) — `invoke_agent`, `execute_tool`, `create_agent`.
- [`gen-ai/gen-ai-events`](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-events/) — prompt/completion content as events.
- [`gen-ai/gen-ai-metrics`](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/) — `gen_ai.client.token.usage`, `operation.duration`.

**How the vendor SDKs plug in**:

- **Langfuse** — accepts OTLP directly (`/api/public/otel`). Also ships its own
  `@observe` decorator for Python that creates OTel-compatible spans.
- **Arize Phoenix** — consumes OTel natively via `openinference-instrumentation-*`
  packages (OpenInference is a small superset of the OTel GenAI conventions that
  Phoenix/Arize backed before OTel merged them).
- **LangSmith** — historically proprietary, but has an OTel-compatible ingest
  endpoint; full fidelity still favours their SDK.
- **Helicone** — proxy-based: you point `base_url` at Helicone, it captures
  request/response and emits its own spans. Good fit for LiteLLM routing; less
  good for custom spans (tool calls, agent turns).
- **Logfire** (Pydantic) — pure OTel, nice Python ergonomics, SaaS only.

For Conexus the pragmatic path is: `opentelemetry-sdk` + `openinference-instrumentation-anthropic`
+ `openinference-instrumentation-litellm` auto-instrument the LLM layer.
Wrap `AgentRegistry.execute_tool` and `handle_agent_message` with manual spans
carrying `conexus.*` attributes. Export OTLP to a local Langfuse.

---

## 4. Self-host vs SaaS tracing

| Platform | License | Self-host | OTel native | Best for |
|----------|---------|-----------|-------------|----------|
| **Langfuse** | MIT | Yes (Docker/K8s, Postgres + ClickHouse) | Yes | Default choice for self-host |
| **Arize Phoenix** | Elastic v2 | Yes (one container) | Yes (OpenInference) | Agent traces + eval workflows |
| **Helicone** | Apache 2.0 | Yes (Docker/K8s) | Partial | Proxy-based multi-provider |
| **LangSmith** | Closed | Enterprise tier only | Partial | LangChain/LangGraph shops |
| **Logfire** | Closed | No | Yes | Teams already on Pydantic/FastAPI |
| **Braintrust** | Closed | No | Yes | Eval-first workflows |

For Conexus: **Langfuse self-hosted** is the right call. Data stays on the Fly
volume, cost is zero, OTel ingest is clean, and it handles prompt management and
evals in the same UI. Phoenix is a strong alternative if agent-graph
visualisation matters more than prompt versioning. Helicone is tempting because
LiteLLM is already in the stack, but losing tool-call spans is a real cost.

---

## 5. Structured logging

Tracing is not logging. You still want line-oriented events for ops: "bot
started", "scheduler fired job X", "budget cap triggered". Use **structlog**
with JSON output and these rules:

**Correlation**: every log line in a request lifecycle carries the same
`trace_id` and `conexus.chat_id`. Bind them once at the edge (Telegram handler)
and let structlog propagate via `contextvars`.

**Event schema** (flat, machine-parseable):

```json
{
  "ts": "2026-04-15T14:03:22-03:00",
  "level": "info",
  "event": "tool.call.complete",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "agent": "pesquisador",
  "chat_id": 1234567,
  "tool": "wiki_search",
  "latency_ms": 184,
  "status": "ok"
}
```

**Redaction**. Never log full prompts at INFO. Define a `redact()` pass that
strips OAuth tokens, Google creds, the Telegram bot token, SSH deploy keys, and
anything matching phone/email regex. Run it on both log payloads and OTel
prompt events. For PII beyond regex, route through a Presidio-style analyzer
(NeMo Guardrails ships one).

---

## 6. Evals

Evals live on two axes:

**Offline** (CI, pre-deploy) vs **online** (prod sampling).
**Deterministic** (asserts) vs **model-graded** (LLM-as-judge).

### Offline datasets

Build a versioned dataset of `(input, expected_behaviour)` pairs. "Expected
behaviour" is rarely a single string — more often it's a set of constraints:
"must cite source", "must answer in pt-BR", "must not call `wiki_delete`". Store
as JSONL in-repo, not in a cloud DB, so CI can diff it.

### Deterministic asserts

Cheap, fast, flakiness-free. Use them first:

- output matches regex / JSON schema
- tool call count ≤ N
- total cost ≤ $X
- latency p95 ≤ Yms
- output language detected as pt-BR
- forbidden tools never called

### LLM-as-judge

Two flavours that matter:

- **Pairwise**: "Given prompt P and two responses A, B — which is better?".
  Reduces judge bias vs absolute scores. Use when comparing prompt/model
  variants.
- **Rubric-graded**: judge scores each response on a fixed rubric
  (correctness, helpfulness, tone, citation). Use for regression over a
  reference dataset.

Always use a stronger model than the one under test as the judge. Calibrate the
judge against human labels on ~50 examples before trusting it.

### Regression suites

A PR that changes `SKILL.md`, a tool signature, or the router should run the
eval suite in CI. Fail on:

1. Any example that regressed from pass to fail.
2. Aggregate judge score drop > 5%.
3. Cost-per-turn regression > 20%.

Store per-run results keyed by `(commit_sha, dataset_version)` so trends are
visible over time.

---

## 7. Eval frameworks

| Framework | Shape | Best for |
|-----------|-------|----------|
| **[DeepEval](https://github.com/confident-ai/deepeval)** | pytest-like, 60+ metrics | Unit tests for LLM behaviour in CI |
| **[Ragas](https://github.com/explodinggradients/ragas)** | scoring lib only | RAG-specific: faithfulness, context precision/recall |
| **[promptfoo](https://github.com/promptfoo/promptfoo)** | YAML + CLI | A/B prompt testing, red-teaming, no SDK |
| **[Inspect AI](https://inspect.ai-safety-institute.org.uk/)** (UK AISI) | MIT, local-only | Capability + safety benchmarks at model layer |
| **OpenAI Evals** | JSON registry | Compatibility with OpenAI's public evals |

Recommended stack for Conexus: **promptfoo** for prompt/model A/B in CI
(Pesquisador's router vs synthesis LLM is exactly its sweet spot), **DeepEval**
for pytest-style agent behaviour tests that live next to `tests/test_agent_handler.py`,
and **Ragas** only if/when the wiki retrieval grows a real ranker. Skip Inspect
unless you start shipping your own fine-tunes.

---

## 8. Guardrails

Guardrails are policies applied to **inputs** and **outputs** independently of
the model. They are not replacements for alignment — they are the belt to the
alignment suspenders.

**Input classifiers** — before the LLM sees the message:

- prompt-injection detection (regex + classifier model)
- jailbreak patterns ("ignore previous instructions", etc.)
- PII detection → redact or refuse
- topic allow/deny (NeMo Guardrails' dialogue rails)

**Output validators** — before the reply hits the user or the tool runs:

- JSON schema validation for structured outputs
- toxicity / hate-speech classifier
- citation grounding (RAG: does the answer appear in retrieved docs?)
- regex / entity scrub on the final message

### Tool comparison

| Tool | Model | Strengths | Weaknesses |
|------|-------|-----------|------------|
| **[NVIDIA NeMo Guardrails](https://github.com/NVIDIA-NeMo/Guardrails)** | Colang DSL + state machine | Dialogue rails, topic control, good PII, integrates Guardrails-AI validators | Steeper learning curve (Colang), LangChain-centric |
| **[Guardrails-AI](https://github.com/guardrails-ai/guardrails)** | Python validator functions | Easy integration, Hub of pre-built validators, composable | Less dialogue-aware |
| **Anthropic prompt shields** (system-prompt hardening + response prefill) | Prompt-engineering patterns | Zero infra, model-native | Model-specific, not a general layer |
| **OpenAI Moderation API** | Hosted classifier | Trivial to call, free tier | Only OpenAI; coverage gaps |
| **Llama Guard / ShieldGemma** | Open-weight classifiers | Self-hostable, fine-tunable | You own the ops |

For Conexus: wrap `handle_agent_message` with a Guardrails-AI input pass (PII +
injection), validate structured tool args with Pydantic (already the case), and
use a lightweight output moderation call only on user-facing replies. Reserve
NeMo for the day a new agent needs strict topic control.

---

## 9. Budget + quota

Conexus already has the right primitives: `BudgetCap`, `CapChecker`,
`UsageTracker`. What's missing is per-model, per-window accounting and
circuit-breaker semantics.

**Per-agent caps** (existing): daily USD cap, `on_exceed: halt|notify`. Keep.

**Per-model caps** (missing): Pesquisador's Gemini Pro synthesis is 20x the
router cost. One runaway `compile_article` can blow the daily cap in a single
call. Add a per-model soft cap that halves `max_tokens` when crossed, hard cap
that refuses.

**Token/cost tracking sources of truth**: keep `UsageTracker` as the enforcement
record. Mirror values onto OTel spans (`conexus.cost_usd`) for analytics but
never read them back for enforcement — spans can be dropped by the exporter.

**LiteLLM Budget Manager** ([docs](https://docs.litellm.ai/docs/budget_manager))
gives per-virtual-key, per-team, per-user budgets with Redis-buffered
Postgres persistence and soft/hard limits. If Conexus ever exposes the LLM
layer as a gateway to a second app, switch enforcement to LiteLLM's proxy and
retire the custom CapChecker. Until then, the custom layer is simpler.

**Circuit breakers**: three patterns worth implementing:

1. *Per-turn tool-call cap* — refuse >15 tool calls in one turn (runaway loop).
2. *Per-minute spend cap* — refuse if last 60s cost > $X (cost spike).
3. *Provider error breaker* — open breaker after N consecutive 5xx from a
   provider; LiteLLM's router already does this, expose it.

---

## 10. Live monitoring

Traces are raw material; you need alerts on derived signals.

**Anomaly detection** — p95 latency, cost-per-turn, and tool-call-count per
agent. Alert when current 1h window exceeds rolling 7d mean + 3σ. Langfuse and
Phoenix both ship this; for Conexus, a nightly query over the trace store into
a small SQLite rollup is enough to start.

**Drift** — embed a daily eval slice (20 canonical prompts) and run it against
production config. Alert when judge score drifts > 5% from last week's baseline.
Catches silent model-side changes (provider A/B tests, version bumps).

**Runaway loops** — metric: `tool_calls_per_turn`. Hard alert at 15. Auto-kill
at 25. The budget cap catches the money but not the wall-clock time.

**Cost spikes** — alert when hourly spend > 2x rolling 24h hourly mean. This
is what Anthropic calls "cost velocity". Dashboards for this in Langfuse are
one panel.

---

## 11. A/B and canary rollouts

Prompts and model choices should ship like code — behind flags, with metrics.

**Prompt versioning**. `SKILL.md` files are already versioned in git, which is
good. What's missing is a runtime binding layer: Langfuse's prompt management
lets you pin `pesquisador@v7` in config, roll v8 to 10% of chats, and compare
judge scores. Even without Langfuse, a simple `prompt_variant` field on the
trace plus a hash-based splitter in `handle_agent_message` gets you 80% of the
value.

**Model canaries**. When swapping the router from Haiku-4 to Sonnet-4.5, route
10% of traffic for 24h, compare: (a) judge score on a replayed prompt set, (b)
cost per turn, (c) tool-call-count distribution, (d) user follow-up rate (a
strong signal: users who reply again within 2 min probably got a bad answer).

**Shadow mode**. For risky changes (new tool, new system prompt), run the new
variant in parallel with the old, log both outputs, serve only the old. After
a week of recorded pairs, decide.

Guardrails for rollouts: (1) automatic rollback on judge score drop > 10%,
(2) no two variants changing at once (isolate the signal), (3) canaries only
on the reactive path — scheduled jobs always run the stable config.

---

## 12. Citations

**OpenTelemetry GenAI**
- [Semantic conventions for GenAI systems](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [GenAI client spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/)
- [GenAI agent & framework spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)
- [GenAI events (prompt/completion content)](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-events/)
- [GenAI metrics](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/)
- [open-telemetry/semantic-conventions (GitHub)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md)

**Tracing platforms**
- [Langfuse (MIT, self-host)](https://langfuse.com/)
- [Arize Phoenix](https://docs.arize.com/phoenix)
- [Helicone](https://www.helicone.ai/)
- [LangSmith](https://docs.smith.langchain.com/)
- [Logfire (Pydantic)](https://logfire.pydantic.dev/)
- [8 AI observability platforms compared (Softcery, 2025)](https://softcery.com/lab/top-8-observability-platforms-for-ai-agents-in-2025)
- [Best LLM tracing tools for multi-agent systems (Braintrust, 2026)](https://www.braintrust.dev/articles/best-llm-tracing-tools-2026)

**Eval frameworks**
- [DeepEval](https://github.com/confident-ai/deepeval)
- [Ragas](https://github.com/explodinggradients/ragas)
- [promptfoo](https://github.com/promptfoo/promptfoo)
- [Inspect AI (UK AISI)](https://inspect.ai-safety-institute.org.uk/)
- [OpenAI Evals](https://github.com/openai/evals)
- [LLM evaluation frameworks head-to-head (Comet)](https://www.comet.com/site/blog/llm-evaluation-frameworks/)

**Guardrails**
- [NVIDIA NeMo Guardrails docs](https://docs.nvidia.com/nemo/guardrails/latest/index.html)
- [NVIDIA-NeMo/Guardrails (GitHub)](https://github.com/NVIDIA-NeMo/Guardrails)
- [Guardrails-AI](https://www.guardrailsai.com/)
- [Guardrails-AI + NeMo integration](https://guardrailsai.com/blog/nemoguardrails-integration)
- [Guardrails tooling comparison (Fuzzy Labs)](https://www.fuzzylabs.ai/blog-post/guardrails-for-llms-a-tooling-comparison)
- [OpenAI Moderation API](https://platform.openai.com/docs/guides/moderation)

**Budget / quota**
- [LiteLLM Budget Manager](https://docs.litellm.ai/docs/budget_manager)
- [LiteLLM Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys)
- [LiteLLM Spend Tracking](https://docs.litellm.ai/docs/proxy/cost_tracking)
- [BerriAI/litellm (GitHub)](https://github.com/BerriAI/litellm)
