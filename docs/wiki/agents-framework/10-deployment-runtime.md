# 10 — Deployment & Runtime Patterns for Long-Running LLM Agents

> Operator reference for Conexus. Assumes Python 3.11+, Fly.io `gru` as the baseline region, Telegram as the primary channel, APScheduler for proactive work, and SQLite on a Fly volume as the default store. Contents here bias toward *what actually runs 24/7* — not toy notebooks.

---

## 1. Executive summary

An LLM agent is not a request/response function — it is a **stateful, long-lived process** with three failure modes a traditional web app does not have: (a) the LLM call itself can hang, time out, or cost money even when it succeeds; (b) tool calls can partially apply side effects before the process crashes; (c) the "work" is often scheduled or event-driven, not user-initiated, so downtime silently drops jobs instead of returning 503s.

The architectural answer is convergent across the industry in 2026: **treat the agent loop as a durable workflow**, persist every tool-call boundary, and make the channel layer (Telegram, Slack, webhooks) a thin adapter over that core. The implementations differ — LangGraph checkpointers, Temporal workflows, Letta's stateful server, DBOS/Restate/Inngest — but the contract is the same: *a crash anywhere between "decide" and "act" must be recoverable without re-billing the user for tokens already spent.*

For Conexus specifically, the current design (single Fly machine in `gru`, SQLite+WAL on a volume, APScheduler with a SQLAlchemy job store, `ping_log` idempotency) is the pragmatic sweet spot for a solo operator running two bots. The sections below document that sweet spot and name the exit ramps when it no longer fits.

---

## 2. Execution models

Pick deliberately — most agents mix several and the boundaries matter.

- **Request / response.** User sends a message, agent replies. Stateless at the HTTP layer, but the conversation must still persist. This is the Telegram `handle_agent_message` path. Budget caps and timeouts live here.
- **Long-running worker.** Process stays up, holds an event loop, owns Telegram long-poll updaters and an APScheduler instance. Single-machine Conexus. Cheap and simple; the whole process is the durability boundary, so crashes lose in-flight tool calls.
- **Scheduled / proactive.** Cron-style triggers fire jobs independent of user input (Ana's morning briefing, Pesquisador's wiki refresh). Requires persistent job store + catchup on boot.
- **Event-driven.** Webhook, Kafka topic, Gmail push, calendar change. Each event is a unit of work; throughput and ordering matter.
- **Streaming.** Token-by-token LLM output, SSE to a frontend, or partial tool-call streaming. Not used in Telegram (final message only) but essential if you ever add a web UI.

Rule of thumb: if a job must run even when the user is asleep and the container restarts, it belongs in the scheduled/durable lane, not the request lane.

---

## 3. State persistence

State for an agent is layered — conversation messages, tool results, long-term memory, and workflow checkpoints are *not the same thing* and rarely share a store.

| Store | Good for | Fails at |
|---|---|---|
| **In-memory dict** | Request-scoped scratch, token counters | Anything past SIGTERM |
| **SQLite (WAL)** | Solo-operator, single machine, ≤ few GB, < 10k writes/min | Multi-writer, horizontal scale, replication |
| **Postgres** | Multi-process, LangGraph `PostgresSaver`, DBOS workflows, serious concurrency | Operational overhead vs SQLite |
| **Redis** | Hot conversation cache, pub/sub between workers, `langgraph-checkpoint-redis` | Durable system-of-record (treat as cache) |
| **DynamoDB / other KV** | Serverless + planetary scale, `DynamoDBSaver` | Relational queries |
| **Durable workflow engines** (Temporal, Restate, DBOS, Inngest) | The *workflow itself* — every tool call becomes a replayable event | Adds an orchestrator you must operate |

For Conexus: `core/memory/sqlite_store.py` holds conversation + ping_log; `wiki_store.py` is git-backed markdown. Both live on `/data` (Fly volume). Enable `PRAGMA journal_mode=WAL; synchronous=NORMAL` — mandatory for any concurrent reader under async.

---

## 4. Checkpointing and resumable agents

A checkpoint is a snapshot of *"what the agent knows and what it was about to do"* written before any external side effect. The production patterns:

- **LangGraph checkpointers.** Every graph step writes a snapshot keyed by `thread_id`. `MemorySaver` for dev; `PostgresSaver`, `SqliteSaver`, Redis, or DynamoDB in prod. Enables resume, time-travel debugging, and human-in-the-loop interrupts mid-graph.
- **Letta's stateful server.** Flips the client/server model: the server owns memory (core + archival), the client sends only new messages. Agents are persistent services, not ephemeral library calls. Good when you want the agent to outlive the caller.
- **Temporal workflows + signals.** The workflow code is deterministic Python; every activity (LLM call, tool call) is recorded in event history. A crash replays history up to the last completed activity — tokens already spent are not re-spent. Signals are how you inject user messages into a running workflow. As of 2026 the OpenAI Agents SDK ships a Temporal integration as GA.
- **DBOS / Restate / Inngest.** Lighter-weight durable execution. DBOS runs on top of Postgres (no extra service), has a Pydantic AI integration, and turns decorated Python functions into replayable steps. Restate is a single-binary engine with first-class "durable agent" primitives. Inngest is SaaS + SDK with event-driven step functions.

Crash recovery contract to enforce regardless of library: **idempotent tool calls, deterministic workflow code, no wall-clock or `random()` outside recorded activities**. If you cannot guarantee determinism, use a checkpointer (LangGraph-style: persist the whole state) rather than replay (Temporal-style: replay history).

For Conexus today: checkpointing is coarse — conversations are persisted message-by-message, but a crash mid-tool-call can re-execute the tool. The mitigation is keeping tools idempotent (wiki commits are `git add`/commit with a deterministic message; `ping_log` guards scheduled sends).

---

## 5. Scheduling

Every serious agent needs a scheduler; the only question is *where it lives*.

- **In-process: APScheduler.** What Conexus uses. `BackgroundScheduler` in an asyncio app, SQLAlchemy job store on the SQLite volume, cron expressions in each agent's `SKILL.md`. Survives restarts because the job store is persistent.
- **Misfires.** A job whose fire-time passed while the process was down is "misfired". APScheduler checks `misfire_grace_time` per job; past that, the job is skipped. Set it to the window where re-running is still meaningful (e.g. 30 min for a morning briefing, `None` for "always catch up").
- **Coalescing.** If the process was down long enough to miss *several* fires of the same cron, `coalesce=True` rolls them into one execution. Usually what you want — nobody needs five morning briefings stacked.
- **Idempotency.** Grace + coalesce are not enough. Write `ping_log(job_id, fire_time)` *before* sending, mark success *after*. On boot, `scheduler.catchup()` re-runs anything missed but still within policy, skipping rows that already show success.
- **Multi-process gotcha.** APScheduler has no cross-process locking. Two Fly machines sharing the same SQLite job store will double-fire. Stay on a single machine or move to Temporal cron / Celery beat / BullMQ (Node) when you need replicas.

Exit ramp: when scheduling graduates to "fan out 1k jobs, retry with backoff, observe per-job status" — move to Temporal (cron workflows), Inngest, or a proper queue (Celery/RQ + Redis, BullMQ if JS).

---

## 6. Async and concurrency

Agents are I/O-bound — LLM latency dwarfs CPU. `asyncio` is the default; threads are for sync libraries you cannot escape.

Patterns that hold up:

- **One event loop, one process.** Run APScheduler's `AsyncIOScheduler` on the same loop as the Telegram updaters; do not mix `BackgroundScheduler` (threads) with async handlers — you will deadlock on SQLite.
- **Tool parallelism.** When the LLM returns N tool calls in one turn, `asyncio.gather` them if independent. Cap concurrency with a `Semaphore(N)` — a 12-tool response hammering the Google Calendar API will trip 429s.
- **Back-pressure.** Every external call needs a timeout (`httpx` default is unbounded — do not ship that). Budget caps (`CapChecker` in Conexus) are themselves back-pressure: stop spending tokens before the LLM runs away.
- **Cancellation hygiene.** Await tasks in `finally` blocks; a SIGTERM during `fly deploy` must drain in-flight tool calls, not orphan them. Structure long jobs as `asyncio.shield` only if the operation is idempotent on retry.
- **Blocking calls.** Any sync HTTP client, `time.sleep`, or heavy CPU work must go through `asyncio.to_thread` or a process pool. The symptom is Telegram updaters stalling for seconds at a time.

---

## 7. Message channels

The agent's job is to be *reachable*. Each channel has quirks worth memorising.

- **Telegram.** Two delivery modes. **Long polling** (`getUpdates`) is what Conexus uses: simpler, works behind NAT, no TLS cert to manage. **Webhooks** push to a public HTTPS endpoint, cut latency to ~100 ms, and reduce API calls by letting you reply in the same HTTP response. Switch to webhooks once you have a stable public URL and want lower latency or higher fan-out. Rate limits: ~30 messages/sec globally, 1 msg/sec per chat; 429s come fast if you broadcast. `python-telegram-bot` handles the loop; two bots in one process means two separate `Application` instances with their own tokens.
- **Slack.** Events API (webhooks) is the default; Socket Mode is the long-poll equivalent for dev/behind-firewall. 3-second ACK deadline — offload work to a background task, respond with a placeholder, update via `chat.update`.
- **Discord.** Gateway (WebSocket, persistent) vs interactions webhook. Bots are typically gateway; slash-command apps can be pure webhook.
- **Webhooks (generic).** Always idempotent on delivery ID. Always verify signatures. Reply fast, process async.
- **Email ingestion.** Gmail push (Cloud Pub/Sub) or IMAP IDLE. Both deliver duplicates under retry — dedupe on `Message-ID`.

Universal rule: the channel adapter parses + enqueues; it does not run the agent loop. Keeps you free to swap Telegram for Slack without touching `handle_agent_message`.

---

## 8. Fly.io / Railway / Modal / Cloud Run

For a 24/7 agent with a volume, the tradeoffs in 2026:

- **Fly.io.** Strong for this shape: cheap always-on VMs (`fly machines`), real block-storage volumes pinned to a region, SSH console, fast deploys, `fly logs` tail. Caveat: a volume is pinned to one host, so **SQLite on a volume means one machine per region** — `fly scale count 1` or `--ha=false`. `gru` gives low latency to Brazil users. This is the Conexus baseline.
- **Railway.** Closest analog to Fly for DX. Persistent volumes up to 50 GB, managed Postgres/Redis, auto-deploys from GitHub. Slightly more opinionated; less regional control than Fly.
- **Modal.** Serverless-ish but supports long-running containers and network volumes. Strong for GPU-bound or bursty workloads; pay per second. Less ideal for a process that must simply *be alive* to hold a Telegram long-poll — you are paying for idle time either way, and the mental model is functions-first.
- **Cloud Run.** Request-scoped by default. The 2024+ "always-allocated CPU" + jobs modes make it viable for agents, but filesystem is ephemeral (use GCS / Cloud SQL for state). Good if you already live in GCP; awkward if your agent needs a local SQLite.

Heuristic: **stateful + small + always-on → Fly or Railway. Bursty + GPU → Modal. Already-on-GCP + willing to use Cloud SQL → Cloud Run.**

---

## 9. Secrets and config

- **Env vars** for non-secrets (region, log level, feature flags). Pydantic Settings reads them typed.
- **Fly secrets** (`fly secrets set`) for API keys, bot tokens, SSH deploy keys. They land as env vars in the machine; never in the image.
- **Doppler / 1Password Connect / Infisical** when you have multiple envs (dev/staging/prod) or multiple humans. These inject at deploy time or runtime via a sidecar/CLI.
- **Never** commit `.env`, `wiki_deploy`, or anything under `/data/`. `.gitignore` and `.dockerignore` should both cover these (Conexus already does).
- **Rotation plan.** If a secret leaks, which commands rotate it? Write that down before you need it — Telegram bot tokens can be revoked via `@BotFather`; Gemini keys via Google AI Studio; Fly secrets via `fly secrets unset && set`.

---

## 10. CI / CD for agent code

Agent code has two test layers traditional apps lack:

- **Unit + integration** (standard). `pytest`, fake LLM fixtures, frozen clocks. Fast feedback — should run on every push in <60 s. Conexus's `tests/conftest.py` (temp SQLite, temp wiki, fake LLM) is the template.
- **Prompt regression / evals.** Snapshot sets of `(input, tool_trace, final_reply)` for canonical scenarios. Run on every change to a `SKILL.md` or prompt-shaping code. Tools: `promptfoo`, `deepeval`, Braintrust, LangSmith. Gate merges on *no regression on the golden set*, not on identical output (LLMs drift).
- **Cost budget in CI.** If your eval suite hits real LLMs, cap it — pin to cheap models, cache fixtures, fail loud if a run exceeds $X.

Deploy shape: GitHub Actions → `fly deploy` on `main`. Keep deploys fast (<3 min) so you iterate; slow pipelines cause drift between "works locally" and "shipped". Health check: a `/healthz` HTTP route that pings the LLM router and checks the SQLite volume mount.

---

## 11. Horizontal scale

The question is *when*, not *if*, SQLite+single-machine stops working. Signals:

- **Write contention.** `database is locked` errors even with WAL. Hits around sustained 100s of writes/sec depending on row size.
- **Multiple channels of ingest** (Telegram + Slack + email + webhooks) producing bursty concurrent writes.
- **Second agent operator** who wants their own instance on the same data.

Migration ladder:

1. **Stay single-process, split stores.** Move hot write paths (ping_log, usage tracker) to Postgres, keep wiki in git, keep conversation in SQLite. Often enough.
2. **Single-agent-per-process, multiple processes.** One Fly machine per agent; each owns its own SQLite. Telegram-side is already sharded by bot token. Scheduler-side needs each process to only schedule its own agent's jobs.
3. **Multi-tenant on Postgres.** All agents share a Postgres; `tenant_id` on every row. APScheduler → Celery beat / Temporal cron. Now you can scale replicas.
4. **Durable workflows.** Replace the bespoke agent loop with Temporal / DBOS. Justified when debugging "what did the agent do three hours ago before it crashed?" becomes a weekly task.

Conexus is firmly at step 1/2 and should stay there as long as it is a solo-operator tool. The current `core/agent_handler.py` + `AgentRegistry` design does not hard-couple to SQLite — the swap is a config change, not a rewrite.

---

## 12. Citations

- [LangGraph Persistence — LangChain docs](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Build durable AI agents with LangGraph and Amazon DynamoDB — AWS](https://aws.amazon.com/blogs/database/build-durable-ai-agents-with-langgraph-and-amazon-dynamodb/)
- [LangGraph + Redis — Redis blog](https://redis.io/blog/langgraph-redis-build-smarter-ai-agents-with-memory-persistence/)
- [Temporal for AI](https://temporal.io/solutions/ai)
- [Durable Execution meets AI — Temporal](https://temporal.io/blog/durable-execution-meets-ai-why-temporal-is-the-perfect-foundation-for-ai)
- [OpenAI Agents SDK + Temporal GA announcement](https://temporal.io/blog/announcing-openai-agents-sdk-integration)
- [Human-in-the-Loop AI Agent — Temporal docs](https://docs.temporal.io/ai-cookbook/human-in-the-loop-python)
- [Letta: Introduction to Stateful Agents](https://docs.letta.com/guides/core-concepts/stateful-agents/)
- [Letta — Stateful Agents blog](https://www.letta.com/blog/stateful-agents)
- [DBOS Transact — Lightweight Durable Python Workflows](https://github.com/dbos-inc/dbos-transact-py)
- [Pydantic AI + DBOS durable execution](https://ai.pydantic.dev/durable_execution/dbos/)
- [Restate — Durable Agents](https://docs.restate.dev/ai/patterns/durable-agents)
- [APScheduler user guide — misfires, coalescing, job stores](https://apscheduler.readthedocs.io/en/3.x/userguide.html)
- [APScheduler FAQ](https://apscheduler.readthedocs.io/en/3.x/faq.html)
- [Fly Volumes overview](https://fly.io/docs/volumes/overview/)
- [Deploy FastAPI + SQLite on Fly.io](https://medium.com/@vladkens/deploy-fastapi-application-with-sqlite-on-fly-io-5ed1185fece1)
- [Fly.io SQLite3 guide](https://fly.io/docs/rails/advanced-guides/sqlite3/)
- [Telegram Bot API FAQ — rate limits](https://core.telegram.org/bots/faq)
- [grammY — Long Polling vs Webhooks](https://grammy.dev/guide/deployment-types)
- [Best agent cloud platforms 2026 — Northflank](https://northflank.com/blog/best-agent-cloud-platforms)
- [Top AI agent runtime tools 2026 — Northflank](https://northflank.com/blog/top-ai-agent-runtime-tools)
- [Modal vs Railway 2026 — Agents Index](https://agentsindex.ai/compare/modal-vs-railway)
