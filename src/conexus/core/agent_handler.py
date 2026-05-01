"""Unified tool-calling message handler for all Conexus agents.

Each agent is described by an AgentHandlerConfig. The single
`handle_agent_message` function runs the tool-calling loop for any agent
without duplicating logic across handlers.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from conexus.core.budget.cap_checker import BudgetCap, CapChecker
from conexus.core.llm.context_tag import set_context
from conexus.core.llm.router import TrackedLLM
from conexus.core.memory.sqlite_store import SqliteStore

_BRT = ZoneInfo("America/Sao_Paulo")


@dataclass
class AgentHandlerConfig:
    name: str                            # "ana" or "pesquisador"
    llm: TrackedLLM
    tools_schema: list[dict]
    execute_tool: Callable[..., Any]     # (name: str, args: dict) -> str, sync or async
    system_prompt: str                   # fixed portion — datetime is appended at call time
    max_turns: int = 10
    cap: BudgetCap | None = None
    cap_exceeded_msg: str = "Orçamento atingido."
    include_facts: bool = False
    progress_map: dict[str, str] | None = None  # tool_name -> Telegram progress text
    result_max_chars: int | None = None          # truncate oversized tool results
    fallback_msg: str = "Não consegui completar."
    tool_tags: dict[str, str] | None = None  # None = TrifectaGuard disabled
    incoming_handoff: object | None = None  # Handoff — typed as object to avoid import cycle


async def handle_agent_message(
    cfg: AgentHandlerConfig,
    store: SqliteStore,
    cap_checker: CapChecker,
    body: str,
    progress: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    """Run the tool-calling agentic loop for any agent.

    Acquires no locks itself — concurrency is handled inside TrackedLLM.acall().
    """
    from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation

    if cfg.cap:
        r = cap_checker.check(cfg.name, cfg.cap)
        if not r.allowed:
            return cfg.cap_exceeded_msg

    if cfg.tool_tags is None:
        guard = None
    elif cfg.incoming_handoff is not None:
        guard = TrifectaGuard.from_handoff(cfg.tool_tags, cfg.incoming_handoff)
    else:
        guard = TrifectaGuard(cfg.tool_tags)

    now_brt = datetime.now(_BRT)
    history = store.chat_recent(cfg.name, limit=10)
    context_lines = "\n".join(f"{m['role']}: {m['content']}" for m in history)

    user_parts: list[str] = []
    if cfg.include_facts:
        facts = store.facts_list()
        facts_lines = "\n".join(f"{f['key']}: {f['value']}" for f in facts) or "(nenhum)"
        user_parts.append(f"Fatos conhecidos:\n{facts_lines}")
    user_parts.append(f"Histórico recente:\n{context_lines}")
    user_parts.append(f"Leandro agora: {body}")

    system = cfg.system_prompt + f"\n\nData/hora atual (BRT): {now_brt.strftime('%Y-%m-%d %H:%M %Z')}"

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]

    _sent_progress: set[str] = set()
    _is_async_tool = inspect.iscoroutinefunction(cfg.execute_tool)

    # Record the user turn up front so history is preserved even if the
    # tool loop exhausts max_turns without producing a text reply.
    store.chat_append(cfg.name, "user", body)

    with set_context("reactive"):
        for _turn in range(cfg.max_turns):
            resp, actual_model = await cfg.llm.acall(
                messages=messages,
                tools=cfg.tools_schema,
                tool_choice="auto",
                temperature=cfg.llm.config.temperature,
            )
            print(f"[llm] {cfg.name} answered: {actual_model}", flush=True)

            choice = resp.choices[0]
            msg = choice.message

            tool_calls = (
                getattr(msg, "tool_calls", None)
                or (msg.get("tool_calls") if isinstance(msg, dict) else None)
            )
            text_content = (
                getattr(msg, "content", None)
                or (msg.get("content") if isinstance(msg, dict) else None)
            )

            if tool_calls:
                messages.append(
                    msg if isinstance(msg, dict) else msg.model_dump(exclude_unset=True)
                )
                for tc in tool_calls:
                    fn_name = (
                        tc.function.name if hasattr(tc, "function") else tc["function"]["name"]
                    )
                    fn_args_raw = (
                        tc.function.arguments
                        if hasattr(tc, "function")
                        else tc["function"]["arguments"]
                    )
                    tc_id = tc.id if hasattr(tc, "id") else tc["id"]
                    try:
                        fn_args = (
                            json.loads(fn_args_raw)
                            if isinstance(fn_args_raw, str)
                            else fn_args_raw
                        )
                    except json.JSONDecodeError:
                        fn_args = {}

                    print(f"[{cfg.name}-tool] {fn_name}({fn_args})", flush=True)

                    if guard:
                        try:
                            guard.check_and_record(fn_name)
                        except (TrifectaViolation, ValueError) as exc:
                            print(f"[trifecta] {cfg.name}: {exc}", flush=True)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": json.dumps({"error": f"TrifectaGuard: {exc}"}),
                            })
                            continue

                    if (
                        progress
                        and cfg.progress_map
                        and fn_name in cfg.progress_map
                        and fn_name not in _sent_progress
                    ):
                        _sent_progress.add(fn_name)
                        await progress(cfg.progress_map[fn_name])

                    result = (
                        await cfg.execute_tool(fn_name, fn_args)
                        if _is_async_tool
                        else cfg.execute_tool(fn_name, fn_args)
                    )

                    if cfg.result_max_chars and len(result) > cfg.result_max_chars:
                        result = result[: cfg.result_max_chars] + "\n[... truncado]"

                    messages.append(
                        {"role": "tool", "tool_call_id": tc_id, "content": result}
                    )
                continue

            reply = text_content or "Pronto."
            store.chat_append(cfg.name, "assistant", reply)
            return reply

    store.chat_append(cfg.name, "assistant", cfg.fallback_msg)
    return cfg.fallback_msg
