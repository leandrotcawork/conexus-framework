"""Ana's proactive jobs. Each builder returns an async JobFn closure over the
tools, LLM, and scheduler state it needs. Main.py wires everything together.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from agents.ana.tools import AnaTools
from core.llm.context_tag import set_context
from core.llm.router import TrackedLLM
from core.memory.sqlite_store import SqliteStore

TZ = ZoneInfo("America/Sao_Paulo")


def _today_range_iso() -> tuple[str, str]:
    now = datetime.now(TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


async def _run_with_ping_log(
    store: SqliteStore,
    kind: str,
    ref_id: str,
    agent_name: str,
    body: Callable[[], Awaitable[str]],
    send_telegram: Callable[[str], Awaitable[None]],
) -> None:
    if store.ping_was_sent(kind, ref_id, agent_name):
        return
    store.ping_mark_pending(kind, ref_id, agent_name)
    try:
        text = await body()
        await send_telegram(text)
        store.ping_mark_sent(kind, ref_id, agent_name)
    except Exception as e:
        import sys
        print(f"[ana:{kind}] failed: {e}", file=sys.stderr)


def make_briefing_job(
    tools: AnaTools,
    llm: TrackedLLM,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    async def run() -> None:
        now = datetime.now(TZ)
        ref_id = now.strftime("%Y-%m-%d")

        async def body() -> str:
            start_iso, end_iso = _today_range_iso()
            events = tools.calendar_list_events(start_iso, end_iso)
            todos = tools.todos_list("open")
            facts = tools.memory_list_facts()

            prompt = (
                "Você é a Ana, secretária do Leandro. Escreva um briefing matinal "
                "curto e caloroso em português brasileiro.\n\n"
                f"Hora atual: {now.strftime('%H:%M')}\n"
                f"Data: {now.strftime('%Y-%m-%d')}\n\n"
                f"Eventos de hoje ({len(events)}):\n"
                + "\n".join(f"- {e['start']}: {e['title']}" for e in events)
                + f"\n\nTodos em aberto ({len(todos)}):\n"
                + "\n".join(f"- {t['text']}" for t in todos)
                + f"\n\nFatos conhecidos:\n"
                + "\n".join(f"- {f['key']}: {f['value']}" for f in facts)
            )

            with set_context("briefing"):
                return await llm.acomplete([
                    {"role": "system", "content": "Você é a Ana."},
                    {"role": "user", "content": prompt},
                ])

        await _run_with_ping_log(
            tools.store, "briefing", ref_id, "ana", body, send_telegram
        )

    return run


def make_recap_job(
    tools: AnaTools,
    llm: TrackedLLM,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    async def run() -> None:
        now = datetime.now(TZ)
        ref_id = now.strftime("%Y-%m-%d")

        async def body() -> str:
            start_iso, end_iso = _today_range_iso()
            events = tools.calendar_list_events(start_iso, end_iso)
            todos = tools.todos_list("open")

            prompt = (
                "Você é a Ana. Escreva um recap noturno curto em pt-BR para o Leandro.\n\n"
                f"Eventos hoje ({len(events)}):\n"
                + "\n".join(f"- {e['start']}: {e['title']}" for e in events)
                + f"\n\nTodos ainda abertos ({len(todos)}):\n"
                + "\n".join(f"- {t['text']}" for t in todos)
            )

            with set_context("recap"):
                return await llm.acomplete([
                    {"role": "system", "content": "Você é a Ana."},
                    {"role": "user", "content": prompt},
                ])

        await _run_with_ping_log(
            tools.store, "recap", ref_id, "ana", body, send_telegram
        )

    return run


def make_pre_event_job(
    tools: AnaTools,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    """Fires every 5 minutes. For each event starting in the next 10-20 minutes
    that hasn't been pinged yet, send a short reminder."""
    async def run() -> None:
        now = datetime.now(TZ)
        window_start = now + timedelta(minutes=10)
        window_end = now + timedelta(minutes=20)
        events = tools.calendar_list_events(window_start.isoformat(), window_end.isoformat())
        for e in events:
            ref_id = e["id"]
            if tools.store.ping_was_sent("pre_event", ref_id, "ana"):
                continue
            tools.store.ping_mark_pending("pre_event", ref_id, "ana")
            try:
                msg = f"⏰ Em ~15 min: {e['title']} ({e['start']})"
                await send_telegram(msg)
                tools.store.ping_mark_sent("pre_event", ref_id, "ana")
            except Exception as ex:
                import sys
                print(f"[ana:pre_event] {ref_id} failed: {ex}", file=sys.stderr)

    return run


def make_todo_sweep_job(
    tools: AnaTools,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    """Fires hourly 09-20. Sends at most one consolidated message per day if
    there are any overdue todos."""
    async def run() -> None:
        now = datetime.now(TZ)
        ref_id = now.strftime("%Y-%m-%d")
        if tools.store.ping_was_sent("todo_sweep", ref_id, "ana"):
            return

        todos = tools.todos_list("open")
        overdue = [t for t in todos if t["due"] and t["due"] < now.isoformat()]
        if not overdue:
            return

        tools.store.ping_mark_pending("todo_sweep", ref_id, "ana")
        try:
            lines = [f"- {t['text']} (era: {t['due']})" for t in overdue]
            msg = "⚠️ Atenção, pendências vencidas:\n" + "\n".join(lines)
            await send_telegram(msg)
            tools.store.ping_mark_sent("todo_sweep", ref_id, "ana")
        except Exception as ex:
            import sys
            print(f"[ana:todo_sweep] failed: {ex}", file=sys.stderr)

    return run


def make_lint_job(
    tools: AnaTools,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    """Weekly wiki lint. v1 stub: just send a "lint stub ran" ack."""
    async def run() -> None:
        now = datetime.now(TZ)
        year, week, _ = now.isocalendar()
        ref_id = f"{year}-{week:02d}"
        if tools.store.ping_was_sent("lint", ref_id, "ana"):
            return
        tools.store.ping_mark_pending("lint", ref_id, "ana")
        try:
            tools.wiki_append_log("lint", f"Weekly lint {ref_id}", "Stub: no issues analyzed yet.")
            await send_telegram(f"🧹 Lint semanal {ref_id}: stub rodou (v1 não analisa ainda).")
            tools.store.ping_mark_sent("lint", ref_id, "ana")
        except Exception as ex:
            import sys
            print(f"[ana:lint] failed: {ex}", file=sys.stderr)

    return run
