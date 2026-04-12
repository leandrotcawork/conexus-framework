"""Conexus entry point. Wires the bot, scheduler, agents, and stores together."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

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

    # --- Bot ---
    async def _handle_ana_message(body: str, _prefix: str) -> str:
        if ana_cap:
            r = cap_checker.check("ana", ana_cap)
            if not r.allowed:
                return "Orçamento diário atingido. Volto amanhã cedinho."
        # v1: simple one-shot pt-BR reply using history + facts
        history = store.chat_recent("ana", limit=10)
        facts = store.facts_list()
        system = f"{ana_skill.frontmatter.goal}\n\n{ana_skill.body}"
        context_lines = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        facts_lines = "\n".join(f"{f['key']}: {f['value']}" for f in facts)
        prompt = (
            f"Fatos conhecidos:\n{facts_lines}\n\n"
            f"Últimas mensagens:\n{context_lines}\n\n"
            f"Usuário agora: {body}"
        )

        with set_context("reactive"):
            reply = ana_llm.complete([
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ])
        store.chat_append("ana", "user", body)
        store.chat_append("ana", "assistant", reply)
        return reply

    async def _handle_usage_cmd(args: str) -> str:
        from datetime import datetime, timedelta, timezone
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
    print("Ana online.", file=sys.stderr, flush=True)

    scheduler.start()
    await scheduler.catchup()

    # Run until terminated
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
