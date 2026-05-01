"""Unified tool-calling message handler for all Conexus agents.

Each agent is described by an AgentHandlerConfig. The single
`handle_agent_message` function runs the tool-calling loop for any agent
without duplicating logic across handlers.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
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


async def handle_team_message(
    *,
    team,
    configs: dict[str, "AgentHandlerConfig"],
    store: "SqliteStore",
    cap_checker: "CapChecker",
    body: str,
    session_id: str | None = None,
    progress: Any = None,
) -> str:
    """Run the team loop: route LLM-emitted delegate_to_<agent> calls between members.

    Starts at team.manager (or first member). Each `delegate_to_<X>` tool call
    builds a Handoff, routes it via HandoffRouter, and pushes a new frame on the
    stack. Returns when the root agent emits a plain-text reply or the
    policy.termination_text is found in any reply.

    Parallel guard: max_parallel_members >= 1 enforced; Phase 9 is serial-only.
    Hop guard: hop_count increments via Handoff.next_hop(); ValueError → tool error.
    Tool audit: every non-delegate tool call is recorded in tool_audit.
    Cross-agent Trifecta: child guard inherits parent guard's tainted_with() snapshot.
    """
    from conexus.core.memory.tool_audit import record_tool_call
    from conexus.core.team.delegate_tool import (
        DELEGATE_PREFIX, build_delegate_schemas, parse_delegate_call,
    )
    from conexus.core.team.handoff import Handoff
    from conexus.core.team.handoff_router import HandoffRouter
    from conexus.core.team.transcript import trim_transcript
    from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation

    if session_id is None:
        session_id = f"sess-{uuid.uuid4().hex[:12]}"

    store.init_db()
    audit_conn: sqlite3.Connection = sqlite3.connect(store.db_path)
    try:
        router = HandoffRouter(team, conn=audit_conn, session_id=session_id)
        policy = team.policy
        termination_text = policy.termination_text

        @dataclass
        class _Frame:
            name: str
            messages: list[dict]
            return_on: str | None
            turns_left: int
            guard: Any
            execute_tool: Any
            is_async_tool: bool
            cfg: AgentHandlerConfig
            last_handoff: Any  # Handoff | None

        def _make_frame(name: str, messages: list[dict], handoff: Any, return_on: str | None) -> _Frame:
            cfg = configs[name]
            if cfg.tool_tags is None:
                g = None
            elif handoff is not None:
                g = TrifectaGuard.from_handoff(cfg.tool_tags, handoff)
            else:
                g = TrifectaGuard(cfg.tool_tags)
            return _Frame(
                name=name, messages=messages, return_on=return_on,
                turns_left=policy.max_turns, guard=g,
                execute_tool=cfg.execute_tool,
                is_async_tool=inspect.iscoroutinefunction(cfg.execute_tool),
                cfg=cfg, last_handoff=handoff,
            )

        starter = team.manager or team.members[0]
        if starter not in configs:
            raise ValueError(f"no AgentHandlerConfig for '{starter}'")

        starter_cfg = configs[starter]
        now_brt = datetime.now(_BRT)
        history = store.chat_recent(starter, limit=10)
        context_lines = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        sys_prompt = (
            starter_cfg.system_prompt
            + f"\n\nData/hora atual (BRT): {now_brt.strftime('%Y-%m-%d %H:%M %Z')}"
        )
        initial_msgs: list[dict] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Histórico recente:\n{context_lines}\n\nLeandro agora: {body}"},
        ]
        store.chat_append(starter, "user", body)

        stack: list[_Frame] = [_make_frame(starter, initial_msgs, None, None)]
        last_reply: str = starter_cfg.fallback_msg

        while stack:
            frame = stack[-1]
            if frame.turns_left <= 0:
                stack.pop()
                continue
            frame.turns_left -= 1

            delegate_schemas = build_delegate_schemas(team, frame.name)
            all_tools = list(frame.cfg.tools_schema) + delegate_schemas

            resp, _ = await frame.cfg.llm.acall(
                messages=frame.messages,
                tools=all_tools,
                tool_choice="auto",
                temperature=frame.cfg.llm.config.temperature,
            )
            msg = resp.choices[0].message
            tool_calls = (
                getattr(msg, "tool_calls", None)
                or (msg.get("tool_calls") if isinstance(msg, dict) else None)
            )
            text_content = (
                getattr(msg, "content", None)
                or (msg.get("content") if isinstance(msg, dict) else None)
            )

            if tool_calls:
                if isinstance(msg, dict):
                    frame.messages.append(msg)
                elif hasattr(msg, "model_dump"):
                    frame.messages.append(msg.model_dump(exclude_unset=True))
                else:
                    frame.messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
                for tc in tool_calls:
                    fn_name = tc.function.name if hasattr(tc, "function") else tc["function"]["name"]
                    fn_args_raw = (
                        tc.function.arguments if hasattr(tc, "function") else tc["function"]["arguments"]
                    )
                    tc_id = tc.id if hasattr(tc, "id") else tc["id"]
                    try:
                        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                    except json.JSONDecodeError:
                        fn_args = {}

                    if fn_name.startswith(DELEGATE_PREFIX):
                        target, payload, opts = parse_delegate_call(fn_name, fn_args)
                        seed_tags = frame.guard.tainted_with() if frame.guard else set()
                        try:
                            if frame.last_handoff is not None:
                                h = frame.last_handoff.next_hop(target).model_copy(update={
                                    "from_agent": frame.name,
                                    "payload": payload,
                                    "context_mode": opts.get("context_mode", "summary"),
                                    "return_on": opts.get("return_on"),
                                    "tags": seed_tags,
                                })
                            else:
                                h = Handoff(
                                    from_agent=frame.name,
                                    to_agent=target,
                                    payload=payload,
                                    context_mode=opts.get("context_mode", "summary"),
                                    return_on=opts.get("return_on"),
                                    max_hops=policy.max_hops,
                                    hop_count=0,
                                    tags=seed_tags,
                                )
                        except ValueError as exc:
                            frame.messages.append({
                                "role": "tool", "tool_call_id": tc_id,
                                "content": json.dumps({"error": f"hop_limit: {exc}"}),
                            })
                            continue
                        try:
                            resolved = router.route(h)
                        except ValueError as exc:
                            frame.messages.append({
                                "role": "tool", "tool_call_id": tc_id,
                                "content": json.dumps({"error": f"route_failed: {exc}"}),
                            })
                            continue
                        child_msgs = trim_transcript(frame.messages, h.context_mode)
                        if not any(m.get("role") == "system" for m in child_msgs):
                            child_msgs.insert(0, {"role": "system", "content": configs[resolved].system_prompt})
                        child_msgs.append({
                            "role": "user",
                            "content": f"Delegated by {frame.name}: {json.dumps(payload['task'])}",
                        })
                        frame.messages.append({
                            "role": "tool", "tool_call_id": tc_id,
                            "content": json.dumps({"delegated_to": resolved}),
                        })
                        stack.append(_make_frame(resolved, child_msgs, h, h.return_on))
                        break  # one delegation per parent turn (max_parallel_members=1 enforcement)
                    else:
                        if frame.guard:
                            try:
                                frame.guard.check_and_record(fn_name)
                            except (TrifectaViolation, ValueError) as exc:
                                blocked = json.dumps({"error": f"TrifectaGuard: {exc}"})
                                frame.messages.append({"role": "tool", "tool_call_id": tc_id, "content": blocked})
                                record_tool_call(
                                    audit_conn, session_id=session_id, agent=frame.name,
                                    tool=fn_name, args=fn_args, result=blocked, outcome="trifecta_blocked",
                                )
                                continue
                        result = (
                            await frame.execute_tool(fn_name, fn_args)
                            if frame.is_async_tool
                            else frame.execute_tool(fn_name, fn_args)
                        )
                        frame.messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})
                        record_tool_call(
                            audit_conn, session_id=session_id, agent=frame.name,
                            tool=fn_name, args=fn_args, result=result, outcome="ok",
                        )
                continue

            reply = text_content or "Pronto."
            last_reply = reply

            if termination_text and termination_text in reply:
                store.chat_append(stack[0].name, "assistant", reply)
                return reply

            if frame.return_on and frame.return_on in reply:
                stack.pop()
                if stack:
                    stack[-1].messages.append({"role": "user", "content": f"[returned from {frame.name}]: {reply}"})
                continue

            stack.pop()
            if stack:
                stack[-1].messages.append({"role": "user", "content": f"[returned from {frame.name}]: {reply}"})

        store.chat_append(starter, "assistant", last_reply)
        return last_reply
    finally:
        audit_conn.close()
