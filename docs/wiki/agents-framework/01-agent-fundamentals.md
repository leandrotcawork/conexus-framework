# 01 — Agent Fundamentals

> Deep reference for building Conexus. Not agent-facing. Primary-source citations at the end.

## 1. Executive summary

- An LLM agent is an **LLM + tools + memory + loop**: a controller model that emits structured actions, a runtime that executes them, and persistent state that survives turns.
- The canonical loop is **observe → think → act → observe** until a terminal `finish_reason` (`stop`) or a watchdog fires (max iterations, budget cap, timeout).
- Three paradigms coexist in 2026: **native function-calling** (OpenAI/Anthropic tool schemas, the default), **ReAct-style prompted reasoning** (Thought/Action/Observation in plaintext, now mostly a fallback for models without tool APIs), and **code-execution agents** (the model writes Python that calls tools as functions — higher expressivity, harder sandboxing).
- State is **layered**: system prompt (identity + invariants) → long-term memory (RAG / wiki) → conversation history → scratchpad (tool results of the current turn). Each layer has a different TTL and budget.
- Determinism is a knob, not a guarantee: `temperature=0`, `seed`, and structured outputs (JSON Schema) reduce variance but never eliminate it. Treat tool-arg parsing as adversarial.

## 2. What is an LLM agent

Formal-ish: an agent is a tuple **(M, T, S, π, τ)** where

- **M** — the LLM policy: `context → distribution over next tokens` (and structured tool calls).
- **T** — a finite set of tools, each a typed function `args → result` with a JSON Schema describing `args`.
- **S** — state: messages + scratchpad + external memory (SQLite, wiki, vector store).
- **π** — the control loop (the "agent harness") that feeds `S` into `M`, dispatches tool calls in `T`, appends results back into `S`.
- **τ** — termination predicate: `finish_reason == "stop"` OR `iters >= max_iters` OR budget/time exceeded.

The LLM is the **brain**; tools are its **hands**; memory is its **long-term self**; the loop is its **nervous system**. Remove any one and you have a chatbot, a RAG endpoint, or a cron job — not an agent.

Conexus maps cleanly: `core/llm/` = M, `agents/<name>/tools.py` + `core/agent_registry.py` = T, `core/memory/` = S, `core/agent_handler.handle_agent_message` = π, and τ is encoded inside that handler plus `core/budget/`.

## 3. The canonical agent loop

```
observe  : append user/tool messages to history
think    : call M(messages, tools=schemas, tool_choice=...)
act      : if response.tool_calls: dispatch each via registry,
           append tool results as role="tool" messages
           else: return assistant content to user
observe' : loop
```

Minimal OpenAI-style Python harness:

```python
def run(messages, tools, dispatch, *, max_iters=8, model="gpt-5"):
    for _ in range(max_iters):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,                 # list of {type:"function", function:{name, parameters}}
            tool_choice="auto",          # "auto" | "required" | "none" | {"type":"function",...}
            parallel_tool_calls=True,    # allow >1 tool_call per step
            temperature=0.2,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if resp.choices[0].finish_reason == "stop":
            return msg.content           # terminal

        for call in (msg.tool_calls or []):
            try:
                args = json.loads(call.function.arguments)
                result = dispatch(call.function.name, args)
            except Exception as e:
                result = {"error": repr(e)}
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result),   # tool results MUST be strings
            })
    raise RuntimeError("max_iters exceeded")
```

**Streaming vs non-streaming.** Streaming yields token deltas and partial `tool_calls` (argument JSON arrives in chunks, reassembled by `index`). Use streaming for user-visible chat (latency-to-first-token matters); use non-streaming inside the loop for tool steps (simpler, atomic, easier to log). Conexus currently runs non-streaming — fine for Telegram.

**`tool_choice`.** `auto` (default) lets the model decide; `required` forces *some* tool call (good for routers/ReAct scaffolds); `none` disables tools for one step (good for final synthesis); `{"type":"function","function":{"name":"X"}}` pins a specific tool.

**Parallel tool calls.** A single assistant turn can emit N `tool_calls`. Dispatch them concurrently (asyncio.gather), but append results **in order of `tool_call_id`** — the model matches them by id, not by position. Set `parallel_tool_calls=False` if a tool has side effects that must serialize.

## 4. ReAct vs function-calling vs code-execution

| Paradigm | Mechanism | When it wins |
|---|---|---|
| **Function-calling** | Model emits a typed JSON `tool_call`; harness validates against schema, dispatches, appends `role="tool"` result. | Default for any modern model. Best tooling, best traces, best latency. This is what Conexus uses. |
| **ReAct** (Yao et al. 2022) | Plaintext `Thought: … Action: tool[args] Observation: …` loop, parsed by regex. | Models without native tool APIs, or when you want the CoT trace in-band for auditing. Fragile parsing; avoid for production. |
| **Code-execution** (CodeAct, Anthropic's code-use, OpenAI's Code Interpreter) | Model writes Python; tools are exposed as Python functions; a sandbox executes and returns stdout/values. | Multi-step data manipulation, math, iteration over results. Higher expressivity per turn (one code block = many tool calls) at the cost of sandbox complexity and arbitrary-code risk. |

Rule of thumb: **function-calling for structured actions, code-execution for compositional data work, ReAct only as a fallback.** Conexus's wiki_search → wiki_read → compile_article chain is pure function-calling; if you ever need "read all 40 wiki pages and aggregate", promote that one agent to code-execution.

## 5. State: conversation history, scratchpad, tool results, system prompt layering

Layer the context in order of decreasing stability:

1. **System prompt (persona + invariants).** Identity, tone, hard rules, current BRT time. Rewrite on every call — it's cheap and it anchors behavior.
2. **Long-term memory.** Retrieved wiki chunks, SQLite facts, calendar snapshot. Inject as a separate `system` or `user` block labelled clearly (`<memory>…</memory>`). Budget: ~20-30% of context.
3. **Conversation history.** `user`/`assistant` pairs. Truncate oldest first; summarize when you cross ~60% of context.
4. **Scratchpad (current turn).** The `assistant.tool_calls` + `tool` results from the in-flight loop. Never truncate mid-turn — the model matches `tool_call_id`s.

Keep these as **separate message arrays** internally, concat at send time. Makes TTL, caching, and debugging tractable. Anthropic's prompt caching keys off prefix stability — put the most stable layer first (system + skill doc), volatile layers last (scratchpad).

## 6. Termination conditions

- **`finish_reason == "stop"`** — natural termination, assistant produced content, no tool calls. Return to user.
- **`finish_reason == "tool_calls"`** — continue the loop.
- **`finish_reason == "length"`** — hit `max_tokens`. Either raise `max_tokens` or summarize and retry. Never treat as success.
- **`max_iters`** — hard cap (6-10 is typical). Prevents runaway tool chains. Conexus should log the final `messages` for postmortem.
- **Self-stop tool.** Give the agent an explicit `finish(summary)` tool when you need a structured terminal action (e.g., Pesquisador's `compile_article`).
- **Watchdogs.** Budget cap (`core/budget`), wall-clock timeout, per-tool call-count cap. All orthogonal to `finish_reason`.

## 7. Error handling

- **Invalid JSON args.** The model occasionally emits malformed JSON. Catch `json.JSONDecodeError`, append a `tool` message with `{"error": "invalid json", "raw": "..."}`, let the model retry. Do not crash.
- **Tool raises.** Wrap every dispatch in `try/except`, return `{"error": repr(e)}` as the tool result. The model self-corrects surprisingly well.
- **Schema-violating args.** Validate args against the JSON Schema (jsonschema / pydantic) before dispatch. Return the validation error as the tool result.
- **Context overflow.** Detect via token count pre-send. Strategies: summarize oldest history into a single `assistant` note, drop old tool results, or fork to a fresh conversation with a handoff summary.
- **Retries.** Retry only on transport errors (5xx, rate limits) with exponential backoff + jitter. Never retry on model logic errors — that's the loop's job.
- **Idempotency.** Tools with side effects (send_message, create_event) need idempotency keys, or the agent will double-fire on retry. Conexus uses `ping_log` for scheduler jobs — extend that pattern to any mutating tool.

## 8. Determinism knobs

- **`temperature`** — 0 for deterministic-ish tool routing, 0.3-0.7 for synthesis. Not a true seed; same input + temp=0 can still differ across model versions.
- **`top_p`** — nucleus sampling cutoff. Prefer `temperature` OR `top_p`, not both.
- **`seed`** (OpenAI) — best-effort reproducibility; returns `system_fingerprint` — if that changes, seed is void.
- **Structured outputs / JSON Schema mode.** OpenAI `response_format={"type":"json_schema", …, "strict": true}`, Anthropic tool-use schemas are strict by construction. Use for any machine-consumed output. Eliminates JSON parse errors.
- **Grammars / constrained decoding** (vLLM, outlines, llama.cpp). When you self-host, this is the strongest guarantee.
- **Prompt caching** (Anthropic, OpenAI). Stable prefix → cache hit → ~10× cost reduction and lower latency variance. Order matters: immutable first.

## 9. Citations

- Lilian Weng — *LLM Powered Autonomous Agents* (2023, still the canonical taxonomy): <https://lilianweng.github.io/posts/2023-06-23-agent/>
- Yao et al. — *ReAct: Synergizing Reasoning and Acting in Language Models* (ICLR 2023): <https://arxiv.org/abs/2210.03629>
- OpenAI — Function calling guide: <https://platform.openai.com/docs/guides/function-calling>
- OpenAI — Structured Outputs: <https://platform.openai.com/docs/guides/structured-outputs>
- Anthropic — Tool use (function calling) overview: <https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview>
- Anthropic — *Building effective agents* (engineering post, 2024): <https://www.anthropic.com/engineering/building-effective-agents>
- Anthropic — Prompt caching: <https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching>
- Simon Willison — *Imitation Intelligence* and agent posts index: <https://simonwillison.net/tags/agents/>
- Simon Willison — *Tool use / function calling notes*: <https://simonwillison.net/tags/tool-use/>
- Wang et al. — *Executable Code Actions Elicit Better LLM Agents* (CodeAct, 2024): <https://arxiv.org/abs/2402.01030>
- LiteLLM — unified tool-calling docs (Conexus uses this): <https://docs.litellm.ai/docs/completion/function_call>
