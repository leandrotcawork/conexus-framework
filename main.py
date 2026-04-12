"""Conexus entry point. Wires the bot, scheduler, agents, and stores together."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from agents.ana.jobs import (
    make_briefing_job,
    make_lint_job,
    make_pre_event_job,
    make_recap_job,
    make_todo_sweep_job,
)
from agents.ana.tools import AnaTools
from core.budget.cap_checker import BudgetCap, CapChecker
from core.config.skill_loader import parse_skill_file
from core.llm.context_tag import set_context
from core.llm.router import LLMConfig, build_llm
from core.llm.usage_tracker import UsageTracker
from core.memory.google_calendar import GoogleCalendarClient
from core.memory.sqlite_store import SqliteStore
from core.memory.wiki_store import WikiStore
from core.messaging.telegram_bot import TelegramBot
from core.scheduler.scheduler import ConexusScheduler, JobSpec


DATA_DIR = Path(os.environ.get("CONEXUS_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "conexus.db"
WIKI_DIR = DATA_DIR / "wiki"

_BRT = ZoneInfo("America/Sao_Paulo")

# Tool schemas in OpenAI function-calling format.
_ANA_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "calendar_list_events",
            "description": "Lista eventos do Google Calendar num intervalo de datas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_iso": {"type": "string", "description": "Início ISO 8601, ex: 2026-04-12T00:00:00-03:00"},
                    "end_iso":   {"type": "string", "description": "Fim ISO 8601"},
                },
                "required": ["start_iso", "end_iso"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create_event",
            "description": "Cria um evento no Google Calendar do Leandro.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":       {"type": "string"},
                    "start_iso":   {"type": "string", "description": "Início ISO 8601"},
                    "end_iso":     {"type": "string", "description": "Fim ISO 8601"},
                    "description": {"type": "string"},
                },
                "required": ["title", "start_iso", "end_iso"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_update_event",
            "description": "Atualiza um evento existente no Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id":    {"type": "string"},
                    "title":       {"type": "string"},
                    "start_iso":   {"type": "string"},
                    "end_iso":     {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_delete_event",
            "description": "Remove um evento do Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_get",
            "description": "Busca um fato específico da memória pelo nome da chave.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_set",
            "description": "Salva um fato na memória persistente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key":   {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_list_facts",
            "description": "Lista todos os fatos salvos na memória.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todos_add",
            "description": "Adiciona uma tarefa/todo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":    {"type": "string"},
                    "due_iso": {"type": "string", "description": "Vencimento ISO 8601 (opcional)"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todos_list",
            "description": "Lista tarefas/todos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["open", "done", "all"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todos_mark_done",
            "description": "Marca uma tarefa como concluída pelo ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_read",
            "description": "Lê um arquivo da wiki de memória.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_list",
            "description": "Lista arquivos da wiki.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_search",
            "description": "Busca conteúdo na wiki.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_write",
            "description": "Escreve ou atualiza um arquivo na wiki.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
]


async def amain() -> None:
    load_dotenv()

    # --- Storage ---
    store = SqliteStore(DB_PATH)
    store.init_db()
    wiki = WikiStore(WIKI_DIR, autocommit=True)

    # --- LLM stack ---
    tracker = UsageTracker(store)
    cap_checker = CapChecker(tracker)

    # --- Load Ana ---
    ana_skill = parse_skill_file("agents/ana/SKILL.md")
    ana_llm_cfg = LLMConfig(
        provider=ana_skill.frontmatter.llm.provider,
        model=ana_skill.frontmatter.llm.model,
        temperature=ana_skill.frontmatter.llm.temperature,
        fallback=[{"provider": f.provider, "model": f.model} for f in ana_skill.frontmatter.llm.fallback],
    )
    ana_llm = build_llm(ana_llm_cfg, tracker, agent_name="ana")
    ana_tools = AnaTools(
        store=store,
        wiki=wiki,
        calendar=GoogleCalendarClient(),
    )
    ana_cap = BudgetCap(
        daily_usd=ana_skill.frontmatter.budget.daily_usd,
        monthly_usd=ana_skill.frontmatter.budget.monthly_usd,
        on_exceed=ana_skill.frontmatter.budget.on_exceed,
    ) if ana_skill.frontmatter.budget else None

    def _execute_tool(name: str, args: dict) -> str:
        """Call an AnaTools method by name and return JSON-serialisable result."""
        fn = getattr(ana_tools, name, None)
        if fn is None:
            return json.dumps({"error": f"ferramenta desconhecida: {name}"})
        try:
            result = fn(**args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # --- Bot ---
    async def _handle_ana_message(body: str, _prefix: str) -> str:
        import litellm

        if ana_cap:
            r = cap_checker.check("ana", ana_cap)
            if not r.allowed:
                return "Orçamento diário atingido. Volto amanhã cedinho."

        now_brt = datetime.now(_BRT)
        history = store.chat_recent("ana", limit=10)
        facts = store.facts_list()

        system = (
            f"{ana_skill.frontmatter.goal}\n\n"
            f"{ana_skill.body}\n\n"
            f"Data/hora atual (BRT): {now_brt.strftime('%Y-%m-%d %H:%M %Z')}\n"
            "Você tem acesso real ao Google Calendar, memória, todos e wiki do Leandro. "
            "Use as ferramentas disponíveis para agir — não apenas descreva o que faria."
        )

        context_lines = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        facts_lines = "\n".join(f"{f['key']}: {f['value']}" for f in facts) or "(nenhum)"

        messages: list[dict] = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"Fatos conhecidos:\n{facts_lines}\n\n"
                    f"Histórico recente:\n{context_lines}\n\n"
                    f"Leandro agora: {body}"
                ),
            },
        ]

        full_model = f"{ana_llm_cfg.provider}/{ana_llm_cfg.model}"

        with set_context("reactive"):
            for _turn in range(6):
                t0 = time.monotonic()
                resp = litellm.completion(
                    model=full_model,
                    messages=messages,
                    tools=_ANA_TOOLS_SCHEMA,
                    tool_choice="auto",
                    temperature=ana_llm_cfg.temperature,
                )
                duration_ms = int((time.monotonic() - t0) * 1000)

                usage = resp.usage
                tracker.log_call(
                    agent_name="ana",
                    provider=ana_llm_cfg.provider,
                    model=ana_llm_cfg.model,
                    input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    context="reactive",
                    duration_ms=duration_ms,
                )

                choice = resp.choices[0]
                msg = choice.message

                # Normalise: message may be object or dict
                tool_calls = getattr(msg, "tool_calls", None) or (msg.get("tool_calls") if isinstance(msg, dict) else None)
                text_content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)

                if tool_calls:
                    # Append assistant turn with tool_calls
                    messages.append(msg if isinstance(msg, dict) else msg.model_dump(exclude_unset=True))
                    for tc in tool_calls:
                        fn_name = tc.function.name if hasattr(tc, "function") else tc["function"]["name"]
                        fn_args_raw = tc.function.arguments if hasattr(tc, "function") else tc["function"]["arguments"]
                        tc_id = tc.id if hasattr(tc, "id") else tc["id"]
                        try:
                            fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                        except json.JSONDecodeError:
                            fn_args = {}
                        print(f"[tool] {fn_name}({fn_args})", flush=True)
                        result = _execute_tool(fn_name, fn_args)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": result,
                        })
                    continue

                # No tool calls → final text reply
                reply = text_content or "Pronto."
                store.chat_append("ana", "user", body)
                store.chat_append("ana", "assistant", reply)
                return reply

        return "Não consegui completar a tarefa."

    async def _handle_usage_cmd(args: str) -> str:
        from datetime import timedelta
        since_days = 30
        if "today" in args:
            since_days = 1
        elif "week" in args:
            since_days = 7
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
        total = tracker.total_usd(agent_name="ana", since=since)
        by_ctx = tracker.by_context(agent_name="ana", since=since)
        lines = [f"📊 Uso últimos {since_days} dia(s)", ""]
        lines.append(f"ana:  US$ {total:.4f}")
        for ctx_name, cost in by_ctx.items():
            lines.append(f"  {ctx_name}: US$ {cost:.4f}")
        return "\n".join(lines)

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    authorized_chat_id = int(os.environ["AUTHORIZED_CHAT_ID"])
    bot = TelegramBot(
        token=token,
        authorized_chat_id=authorized_chat_id,
        message_handler=_handle_ana_message,
        usage_command_handler=_handle_usage_cmd,
    )
    app = bot.build()

    async def send_to_leandro(text: str) -> None:
        await bot.send_message(text)

    # --- Scheduler ---
    scheduler = ConexusScheduler(store, tz="America/Sao_Paulo")
    scheduler.add_job(JobSpec("ana", "briefing",   "0 7 * * *",
                              make_briefing_job(ana_tools, ana_llm, send_to_leandro)))
    scheduler.add_job(JobSpec("ana", "recap",      "0 21 * * *",
                              make_recap_job(ana_tools, ana_llm, send_to_leandro)))
    scheduler.add_job(JobSpec("ana", "pre_event",  "*/5 * * * *",
                              make_pre_event_job(ana_tools, send_to_leandro)))
    scheduler.add_job(JobSpec("ana", "todo_sweep", "0 9-20 * * *",
                              make_todo_sweep_job(ana_tools, send_to_leandro)))
    scheduler.add_job(JobSpec("ana", "lint",       "0 22 * * 0",
                              make_lint_job(ana_tools, send_to_leandro)))

    # --- Start everything ---
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("Ana online.", flush=True)

    scheduler.start()
    await scheduler.catchup()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(amain())
