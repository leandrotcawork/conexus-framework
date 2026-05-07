# Agents Framework Wiki — Second Brain

Local-only research wiki. Purpose: comprehensive reference on LLM agent
engineering so Conexus can adopt best-in-class patterns instead of
reinventing. Not deployed, not agent-facing — this is *our* map.

## Partitions

| # | File | Topic |
|---|------|-------|
| 01 | [agent-fundamentals.md](01-agent-fundamentals.md) | What an agent is, LLM-as-brain loop, ReAct, tool-calling mechanics |
| 02 | [frameworks-survey.md](02-frameworks-survey.md) | LangChain/LangGraph, OpenAI Agents SDK, Anthropic SDK+Skills, CrewAI, Letta, smolagents, PydanticAI, Mastra, AutoGen, DSPy |
| 03 | [tools-design.md](03-tools-design.md) | Tool schemas, typing, validation, error handling, tool selection heuristics |
| 04 | [memory-systems.md](04-memory-systems.md) | Short/long-term, episodic, semantic, vector vs SQL vs wiki, Mem0, Letta/MemGPT, Zep |
| 05 | [skills-prompts.md](05-skills-prompts.md) | Anthropic Skills, system prompts, persona, dynamic context injection, prompt caching |
| 06 | [multi-agent-orchestration.md](06-multi-agent-orchestration.md) | Supervisor, swarm, handoffs, A2A protocol, graphs, crews |
| 07 | [rag-and-wiki.md](07-rag-and-wiki.md) | Embeddings, hybrid search, GraphRAG, git-backed wikis, self-updating knowledge |
| 08 | [planning-reasoning.md](08-planning-reasoning.md) | Plan-execute, Reflexion, ToT, chain-of-agents, self-critique |
| 09 | [observability-evals.md](09-observability-evals.md) | Tracing (Langfuse, Arize, LangSmith), evals, guardrails, budget |
| 10 | [deployment-runtime.md](10-deployment-runtime.md) | Long-running agents, scheduling, async, webhooks, resumable state |
| 11 | [mcp.md](11-mcp.md) | Model Context Protocol — servers, clients, security, ecosystem |
| 12 | [cost-token-optimization.md](12-cost-token-optimization.md) | Prompt caching, context compression, model routing, batching |
| 13 | [conexus-gap-analysis.md](13-conexus-gap-analysis.md) | Current Conexus vs best-in-class — concrete gaps |
| 14 | [conexus-target-architecture.md](14-conexus-target-architecture.md) | Target design — what we adopt, adapt, or keep |
| 15 | [future-vision.md](15-future-vision.md) | Direction beyond v2 — marketplace, UI, A2A, signed packs, sandboxing |
| 16 | [tutorial-create-agent.md](16-tutorial-create-agent.md) | How to create a single agent — SKILL.md, tools.py, tests, CLI REPL, Telegram registration |
| 17 | [tutorial-create-team.md](17-tutorial-create-team.md) | How to create a team — TEAM_PACK.md, edges, budget cascader, delegate_to, replay |
| 18 | [tutorial-deploy.md](18-tutorial-deploy.md) | Local dev + Fly.io deployment — env vars, secrets checklist, Dockerfile, volumes, SSH key injection, MCP server |
| 19 | [tutorial-runtime-flow.md](19-tutorial-runtime-flow.md) | Boot sequence, single-agent loop, tool execution, TrifectaGuard, budget cap, multi-agent stack, audit/replay, extension cookbook |
| 20 | [connector-marketplace.md](20-connector-marketplace.md) | Remote MCP connector marketplace — ConnectorPack format, OAuth 2.1 / PKCE / DCR auth flow, AES-GCM vault, ConnectorRegistry, CLI, security model |
| 21 | [conexus-studio.md](21-conexus-studio.md) | Conexus Studio local web UI — FastAPI admin sub-app, `make_admin_app` factory, AdminContext DI, HTMX/Alpine/Tailwind stack, `conexus studio` CLI subcommand |

## Reading order

First pass: 01 → 02 → 11 (MCP is foundational now).
Second pass: 03 → 04 → 05 → 07 (core engineering).
Third pass: 06 → 08 → 09 → 10 → 12 (advanced).
Synthesis: 13 → 14.
Direction: 15 (intent only, not commitment).
Tutorials (ship something): 16 → 17 → 18 → 19.
Connector marketplace: 20 (auth flow + security model) → then 16 §9 (install + wire).
Studio UI: 21 (Wave 0 scaffold → Wave 1 agent/connector/REPL views → Phase A 4-layer capability tab → Phase C unified packs registry → Phase D pack install/uninstall).

## Conventions

- Each partition: executive summary, deep technical section, code/config snippets, citations with URLs.
- Frameworks cited by repo or official docs URL.
- Opinionated verdicts allowed — mark `> Verdict:` blocks.
- Keep living — update as frameworks evolve (landscape moves monthly).
