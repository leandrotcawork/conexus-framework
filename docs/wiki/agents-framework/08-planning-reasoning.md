# 08 — Planning & Reasoning Patterns for LLM Agents

Audience: senior engineers (and Claude) working on Conexus. This is a reference, not a tutorial.
It catalogues the planning/reasoning patterns relevant to a tool-calling agent framework, with
concrete algorithm sketches, failure modes, and notes on when each applies to Conexus's current
shape (single tool-calling loop in `core/agent_handler.py`, per-agent `SKILL.md`, LiteLLM router).

---

## 1. Executive summary

An agent's "brain" is a loop over three capabilities: **reason** (decide next step), **act**
(call a tool), **observe** (read the result). Every published pattern is a different way of
slicing that loop:

- **ReAct** — fuse reason+act+observe into one token stream. Baseline for tool-use agents.
- **Plan-and-Execute / Plan-and-Solve** — separate the planner from the executor; cheaper,
  more controllable, but brittle if the world changes mid-plan.
- **ReWOO** — plan once with tool placeholders, resolve observations at the end. ~5× token
  savings on multi-hop QA.
- **Reflexion / self-critique** — add a verbal RL loop: execute → critique → retry.
- **Tree / Graph of Thoughts** — branch and evaluate multiple reasoning paths; expensive,
  only pays off on search-shaped problems.
- **Chain-of-Agents / LLM-as-compiler** — decompose long-context work across specialised
  sub-agents or compile the plan into a DAG of parallel calls.
- **Extended thinking / reasoning models** — the provider runs the search loop internally
  (Claude extended thinking, OpenAI o-series, DeepSeek R1). Often replaces an agentic loop
  for purely cognitive tasks, but does **not** replace tool orchestration.
- **Structured planning artefacts** — TODO files, subtask trees, DAGs as the agent's
  external memory (Claude Code, Cursor, Aider).

Rule of thumb: **start with ReAct + tool-use. Add planning only when you observe failure
modes that planning fixes** (wasted tool calls, wrong ordering, re-doing work).

---

## 2. ReAct — reason+act interleaved (the baseline)

Yao et al., 2022. Interleave `Thought → Action → Observation` tokens in a single
completion. The thought grounds the next action; the observation grounds the next thought.
This is exactly what Conexus's `handle_agent_message` does — modern function-calling APIs
(OpenAI, Anthropic tool_use) are ReAct with a typed action channel.

Sketch:

```
loop:
    msg = llm(history)
    if msg.tool_calls:
        for call in msg.tool_calls:
            history += ToolResult(registry.execute(call))
    else:
        return msg.content
```

**Strengths.** Simple; streams naturally; the model adapts to observations (handles 404s,
empty search results, tool errors). State-of-the-art on interactive benchmarks (ALFWorld,
WebShop) vs. pure CoT or imitation learning.

**Failure modes.**
- **Thought-drift loops** — model keeps "thinking" without calling a tool. Cap with
  `max_iterations` (Conexus's handler already does this).
- **Redundant tool calls** — no memory of what was already fetched. Fix with a
  deduplicating tool cache or a planner.
- **Late binding of goals** — by step 8, the model has forgotten the user's original ask.
  Fix by re-injecting the goal into the system prompt or using a plan.
- **No global ordering** — ReAct is locally greedy; it can't "first gather all inputs,
  then synthesise" unless you tell it to.

---

## 3. Plan-and-Execute / Plan-and-Solve

Wang et al., 2023 ("Plan-and-Solve Prompting"). Split the loop into two LLMs (or two
phases): a **planner** writes a numbered plan, an **executor** carries out each step with
tools. LangGraph's `plan_execute` and `plan_and_execute` agent ship this pattern.

Sketch:

```
plan: list[Step] = planner_llm(goal, system="Decompose into numbered subtasks.")
for step in plan:
    result = executor_llm_react(step, tools=...)
    trace.append(result)
    if replan_needed(result): plan = planner_llm(goal, trace)
return synthesiser_llm(goal, trace)
```

**Why it helps.** The planner sees the whole task in one shot (fewer semantic misses, fewer
missed steps — the Plan-and-Solve paper's main empirical gain over Zero-shot-CoT). The
executor can be a cheap model because the "thinking" is done.

**Cost model.** 1 planner call + N cheap executor calls, vs. ReAct's N expensive calls.
Good when the planner model is smarter than needed for individual steps (e.g. Pesquisador's
Gemini Pro synthesis vs. the cheap router model).

**Failure modes.** Plans go stale — if step 3 reveals the plan was wrong, naïve
plan-and-execute plows on. Mitigate with a `replan` hook after each step, or by marking
steps as "hypothesis" the executor can override.

---

## 4. ReWOO — plan without observations

Xu et al., 2023. Observation that ReAct pays a huge token tax by re-feeding the full
history (thought₁ + obs₁ + thought₂ + obs₂ + …) into every call. ReWOO generates the
**entire plan with placeholders for tool outputs** in one shot, runs all tools (possibly in
parallel), then calls a solver once with all observations.

Sketch:

```
plan = planner_llm(goal)              # "Plan: #1 search(x) -> #E1 ; #2 lookup(#E1) -> #E2 ; ..."
evidence = {}
for step in topological_order(plan):
    args = substitute(step.args, evidence)
    evidence[step.id] = tools[step.tool](args)
return solver_llm(goal, plan, evidence)
```

**Token savings.** ~5× on HotpotQA vs. ReAct; ~4% accuracy gain. The win comes from each
tool result being fed in exactly once, to the solver.

**When it fits Conexus.** Pesquisador's research pipeline is a near-perfect ReWOO shape:
the router could emit a plan ("search these 5 queries, fetch these URLs, then compile"),
fan out the HTTP calls, and hand the bag of sources to `compile_article` (Gemini Pro) once.
Don't use it when later steps genuinely depend on earlier *decisions* (not just values) —
that's ReAct territory.

---

## 5. Reflexion + self-critique

Shinn et al., 2023. "Verbal reinforcement learning": after a failed attempt, the agent
writes a natural-language reflection ("I assumed the API returned a list but it's a dict")
and stores it in an episodic buffer. Next attempt, the reflection is prepended.

Three roles:

```
actor      = react_agent(tools)
evaluator  = fn(trajectory) -> scalar | bool | nl-critique
reflector  = llm(trajectory, evaluator_output) -> lesson
memory     = list[lesson]          # grows across trials

for trial in range(K):
    trajectory = actor.run(task, hints=memory)
    score = evaluator(trajectory)
    if score == pass: break
    memory.append(reflector(trajectory, score))
```

91% HumanEval vs. 80% GPT-4 baseline in the paper. In practice for Conexus:

- **Evaluator.** For code tasks: run tests. For research: check citations resolve. For
  Ana: schema-validate the tool_call output. Cheap deterministic evaluators beat LLM
  critics when available.
- **Reflector cadence.** Once per trial, not per step — per-step critiques devolve into
  anxious self-doubt that burns tokens without improving quality.
- **Memory hygiene.** Bound the buffer (top-K most recent/relevant), or the agent
  eventually reads its own neuroses as context.

---

## 6. Tree-of-Thoughts, Graph-of-Thoughts

Yao et al., 2023 (ToT); Besta et al., 2023 (GoT). Instead of one reasoning trace, branch
into k candidate thoughts at each step, score them with an LLM evaluator, keep the
top-b (beam search) or explore via BFS/DFS. GoT generalises to DAGs with aggregation
nodes (merge two branches).

```
frontier = [root_thought]
for depth in range(D):
    children = flatten(expand(t, k=5) for t in frontier)
    scored   = [(evaluate(c), c) for c in children]
    frontier = topk(scored, b=3)
return best(frontier)
```

**When it pays.** Narrow search problems where (a) candidate steps are cheap to generate,
(b) an LLM can rank them meaningfully, (c) the task has a clean success signal (Game-of-24
went from 4% to 74% on GPT-4). Puzzles, program synthesis, constrained generation.

**When it's overkill.** Almost all agentic work. A Telegram reply does not need a search
tree. The k×D token multiplier and the evaluator overhead destroy latency. Unless you can
point at a concrete search frontier, don't reach for ToT.

---

## 7. Chain-of-Agents, LLM-as-compiler

**Chain-of-Agents** (Zhang et al., 2024, NeurIPS) handles long context by sharding: worker
agents process chunks sequentially, each passing a running summary ("communication unit")
to the next; a manager aggregates. Beats RAG and long-context baselines on tasks requiring
cross-chunk reasoning.

**LLM-as-compiler** (LLMCompiler, Kim et al., 2023) treats the LLM as a planner that emits
a **DAG of tool calls** with dataflow dependencies, then a runtime executes the DAG with
parallelism and dependency resolution. Similar spirit to ReWOO but with explicit parallel
scheduling. 3.7× latency reduction on embarrassingly parallel tool use.

For Conexus: if Pesquisador ever needs to cross 20 sources, a CoA-style shard
(`search → per-source-summary → merge`) beats dumping everything into one prompt. The
`jobs.py` scheduler + `AgentRegistry` already give us the primitives.

---

## 8. Extended thinking vs. agentic loops

Reasoning-tuned models (Claude extended/adaptive thinking; OpenAI o1, o3, o4-mini;
DeepSeek-R1; Gemini thinking) run an internal search loop before producing tokens. The
provider bills for the thinking tokens; the client sees a `thinking` block (or summary)
plus the answer.

Claude specifics (relevant for Conexus's LiteLLM stack):

- `thinking={"type":"enabled","budget_tokens":N}` — deprecated on Opus 4.6 / Sonnet 4.6 in
  favour of **adaptive thinking** (automatic budget).
- **Interleaved thinking with tool use** — Claude can think *between* tool calls, not just
  at the start. Sonnet 4.6 / Opus 4.6 enable this automatically; earlier 4-series needs
  the `interleaved-thinking-2025-05-14` beta header. When you preserve `thinking` blocks
  across turns, the model keeps the latent chain alive across tool results.
- **You must pass `thinking` blocks back** with tool results or the next turn loses the
  reasoning state.

**When to use reasoning models vs. agentic planning.**

| Task shape                                     | Pick                         |
|-----------------------------------------------|------------------------------|
| Pure cognition (math, logic, code refactor)    | Reasoning model, no loop     |
| Tool-heavy but short (≤3 tools, linear)        | ReAct + adaptive thinking    |
| Tool-heavy, parallel, known structure          | ReWOO / LLMCompiler          |
| Open-ended, long-horizon, user-facing          | Plan-and-Execute + reflexion |
| Needs backtracking over candidate solutions    | ToT with a reasoning model as scorer |

Reasoning models do **not** remove the need for an outer agentic loop when real-world
side-effects (Telegram sends, git commits, calendar writes) are involved — they just make
each "thought step" smarter.

---

## 9. Structured planning artefacts

The industrial pattern: treat the plan as a **file**, not a prompt. It becomes durable
memory, a diff target, and a UX surface.

- **Claude Code** — the TodoWrite tool maintains an in-session todo list with statuses
  (`pending`, `in_progress`, `completed`). The model re-reads it each turn; users see
  progress; abandoned items are visible.
- **Cursor** — the Agent mode keeps a scratch plan and streams checkmarks as steps land.
- **Aider** — maintains a repo map and a `CONVENTIONS.md` that frames every turn; commits
  are the atomic plan units.
- **Devin / OpenHands** — full subtask trees persisted to disk; the agent can pause,
  resume, and hand off.

Shapes to know:

- **Linear TODO list** — cheap, works for ≤10 steps.
- **Subtask tree** — parent task decomposes into leaves; good for code features.
- **DAG** — explicit dependencies; enables parallel execution and ReWOO-style batching.
- **Kanban/state machine** — for long-running work (this is why Conexus logs to SQLite +
  `ping_log`).

Implementation hint for Conexus: a `plan.md` per long-running task, committed to the wiki,
gives us Aider-style durability for free and plays nicely with the existing git-backed
`WikiStore`.

---

## 10. Self-repair patterns

The core insight: **the cheapest critic is a deterministic one**.

- **Retry-with-critique.** Tool returns an error → feed the error back verbatim in the
  next turn. Modern APIs do this implicitly via `tool_result` with `is_error=True`.
- **Linter-in-the-loop.** After every code edit, run `ruff`/`mypy`/`pytest`; if it fails,
  the next turn's first input is the failure. (Aider, Cursor, Claude Code all do this.)
- **Test-driven iteration.** Write test first, then loop edit→run→edit until green. The
  test suite is the evaluator in the Reflexion sense.
- **Schema-guarded outputs.** Pydantic-validate tool args and responses; on failure,
  return the `ValidationError` as the tool result. Conexus already does this via typed
  tool methods + `schema_gen`.
- **Double-check pass.** For high-stakes outputs (a scheduled Telegram message, a wiki
  commit), a cheap second model reviews before send. Cost: ~5% extra; benefit:
  catches the obvious hallucinations.

Anti-pattern: LLM-critiquing-LLM with no ground truth signal. It feels rigorous and
produces beautifully confident wrong answers.

---

## 11. When NOT to plan

Planning has a floor cost (a whole extra LLM call, plus context bloat). For small tasks,
ReAct with 1–2 tool calls beats any plan.

Skip planning when:

- The task fits in one tool call ("what's the weather", "send this message").
- Latency matters more than optimality (chat replies, Telegram).
- The tool surface is small (≤3 tools) and orthogonal.
- You have a reasoning model — let it plan internally.
- You can't define "good plan" (creative tasks, open-ended chat).

Conexus's Ana is mostly in this regime. Pesquisador's `compile_article` is not — research
benefits from explicit planning.

---

## 12. Evaluation

Three axes, measured separately:

- **Plan quality** (if you have an explicit plan).
  - Coverage: does the plan mention every required subtask? (LLM-judge vs. gold plan.)
  - Ordering: are dependencies respected? (DAG validity check.)
  - Minimality: no redundant steps. (Count vs. gold.)
- **Execution success.**
  - End-to-end task success rate on a fixed eval set.
  - Tool-call success rate (non-error results / total calls).
  - Step accuracy: % of individual steps that produced the expected observation.
- **Efficiency.**
  - Tokens per resolved task.
  - Wall-clock per task.
  - $ per task (Conexus already tracks via `UsageTracker`).

Keep a regression set of ~30 real tasks per agent. Run it on every SKILL.md / prompt
change. Cheaper than you'd think; catches silent regressions that vibes-testing misses.

---

## 13. Citations

- Yao et al., **"ReAct: Synergizing Reasoning and Acting in Language Models"**, ICLR 2023.
  <https://arxiv.org/abs/2210.03629>
- Shinn et al., **"Reflexion: Language Agents with Verbal Reinforcement Learning"**,
  NeurIPS 2023. <https://arxiv.org/abs/2303.11366>
- Wang et al., **"Plan-and-Solve Prompting"**, ACL 2023. <https://arxiv.org/abs/2305.04091>
- Xu et al., **"ReWOO: Decoupling Reasoning from Observations for Efficient Augmented
  Language Models"**, 2023. <https://arxiv.org/abs/2305.18323>
- Yao et al., **"Tree of Thoughts: Deliberate Problem Solving with LLMs"**, NeurIPS 2023.
  <https://arxiv.org/abs/2305.10601>
- Besta et al., **"Graph of Thoughts"**, AAAI 2024. <https://arxiv.org/abs/2308.09687>
- Zhang et al., **"Chain of Agents: Large Language Models Collaborating on Long-Context
  Tasks"**, NeurIPS 2024. <https://arxiv.org/abs/2406.02818>
- Kim et al., **"An LLM Compiler for Parallel Function Calling"**, ICML 2024.
  <https://arxiv.org/abs/2312.04511>
- Anthropic, **"Extended thinking"** / **"Adaptive thinking"** docs.
  <https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking>
- OpenAI, **"Reasoning models (o-series)"** guide.
  <https://platform.openai.com/docs/guides/reasoning>
- DeepSeek-AI, **"DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via RL"**, 2025.
  <https://arxiv.org/abs/2501.12948>
- LangGraph, **Plan-and-Execute agent tutorial**.
  <https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/plan-and-execute/>
