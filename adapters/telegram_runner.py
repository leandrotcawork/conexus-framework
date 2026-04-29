"""Consumer wiring: SSH, stores, agents, bots, and scheduler for the Conexus runtime."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
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
from agents.pesquisador.jobs import (
    make_proactive_research_job,
    make_weekly_digest_job,
    make_wiki_audit_job,
)
from agents.pesquisador.tools import PesquisadorTools
from conexus.core.agent_handler import handle_agent_message
from conexus.core.agent_registry import AgentRegistry
from conexus.core.budget.cap_checker import CapChecker
from conexus.core.llm.router import LLMConfig, build_llm
from conexus.core.llm.usage_tracker import UsageTracker
from conexus.core.memory.google_calendar import GoogleCalendarClient
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore
from conexus.core.messaging.telegram_bot import TelegramBot
from conexus.core.config.skill_loader import parse_skill_file
from conexus.core.scheduler.scheduler import ConexusScheduler, JobSpec
from conexus.cli.runner import build_runtime


def _install_ssh_key(key_content: str, filename: str) -> Path:
    """Write a deploy key to ~/.ssh and add GitHub to known_hosts. Returns key path."""
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    key_file = ssh_dir / filename
    key_file.write_text(key_content + "\n")
    key_file.chmod(0o600)
    subprocess.run(
        ["ssh-keyscan", "-t", "ed25519", "github.com"],
        stdout=open(ssh_dir / "known_hosts", "a"),
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    print(f"[wiki] SSH deploy key configured ({key_file})", flush=True)
    return key_file


def _clone_or_pull(repo_url: str, local_dir: Path, key_file: Path | None) -> None:
    """Clone repo if missing, pull if exists. Switches remote to SSH when key is set."""
    import shutil
    ssh_cmd = f"ssh -i {key_file} -o StrictHostKeyChecking=accept-new" if key_file else None
    env = {**os.environ, "GIT_SSH_COMMAND": ssh_cmd} if ssh_cmd else None
    # Use SSH URL directly when a deploy key is available (required for private repos).
    clone_url = repo_url
    if key_file:
        clone_url = re.sub(
            r"https://github\.com/(.+?)(?:\.git)?$",
            r"git@github.com:\1.git",
            repo_url,
        )
    if not (local_dir / ".git").exists():
        # If the dir has leftover files from a pre-git run, clear them so
        # git clone (which refuses non-empty destinations) can succeed.
        if local_dir.exists() and any(local_dir.iterdir()):
            print(f"[wiki] {local_dir.name} has no .git — clearing for fresh clone...", flush=True)
            sentinel = local_dir / ".conexus-clone-target"
            if not sentinel.exists():
                raise RuntimeError(
                    f"Refusing to clear {local_dir}: .conexus-clone-target sentinel absent. "
                    "Verify CONEXUS_DATA_DIR is correct."
                )
            shutil.rmtree(str(local_dir))
        print(f"[wiki] Cloning {clone_url} → {local_dir}...", flush=True)
        subprocess.run(
            ["git", "clone", clone_url, str(local_dir)],
            check=True, capture_output=True, text=True, timeout=60, env=env,
        )
        (local_dir / ".conexus-clone-target").touch()
    else:
        print(f"[wiki] Pulling {local_dir.name}...", flush=True)
        try:
            branch_result = subprocess.run(
                ["git", "-C", str(local_dir), "rev-parse", "--abbrev-ref", "HEAD"],
                check=True, capture_output=True, text=True, timeout=5, env=env,
            )
            branch = branch_result.stdout.strip()
            if not branch or branch == "HEAD":
                default_result = subprocess.run(
                    ["git", "-C", str(local_dir), "symbolic-ref", "refs/remotes/origin/HEAD", "--short"],
                    check=True, capture_output=True, text=True, timeout=5, env=env,
                )
                branch = default_result.stdout.strip().removeprefix("origin/")
            subprocess.run(
                ["git", "-C", str(local_dir), "checkout", branch],
                check=True, capture_output=True, text=True, timeout=10, env=env,
            )
            subprocess.run(
                ["git", "-C", str(local_dir), "pull", "--ff-only"],
                check=True, capture_output=True, text=True, timeout=30, env=env,
            )
        except subprocess.CalledProcessError as e:
            print(f"[wiki] pull setup failed for {local_dir}: {e}", file=sys.stderr)
            return
    if key_file and (local_dir / ".git").exists():
        ssh_url = re.sub(
            r"https://github\.com/(.+?)(?:\.git)?$",
            r"git@github.com:\1.git",
            repo_url,
        )
        if ssh_url != repo_url:
            subprocess.run(
                ["git", "-C", str(local_dir), "remote", "set-url", "origin", ssh_url],
                capture_output=True, text=True,
            )
            print(f"[wiki] remote switched to SSH: {ssh_url}", flush=True)


async def run() -> None:
    load_dotenv()

    data_dir = Path(os.environ.get("CONEXUS_DATA_DIR", "/data"))
    db_path = data_dir / "conexus.db"
    wiki_dir = data_dir / "wiki"

    # --- Storage ---
    store = SqliteStore(db_path)
    store.init_db()
    # NB: `wiki` (WikiStore) is constructed below, after the repo is cloned,
    # so we can pass the right ssh_cmd for pushes. Do not instantiate it here.

    # --- SSH deploy keys ---
    ana_deploy_key = os.environ.get("ANA_WIKI_DEPLOY_KEY", "")
    pesq_deploy_key = os.environ.get("GITHUB_WIKI_DEPLOY_KEY", "")

    ana_key_file: Path | None = None
    pesq_key_file: Path | None = None

    if ana_deploy_key:
        ana_key_file = _install_ssh_key(ana_deploy_key, "ana_deploy")
    if pesq_deploy_key:
        pesq_key_file = _install_ssh_key(pesq_deploy_key, "pesquisador_deploy")

    # GIT_SSH_COMMAND: use a wrapper that picks the right key per host.
    # Since both remotes are github.com we set it to the pesquisador key by default
    # and override per subprocess call via env= where needed.
    if pesq_key_file:
        os.environ["GIT_SSH_COMMAND"] = f"ssh -i {pesq_key_file} -o StrictHostKeyChecking=accept-new"

    # --- Ana Wiki ---
    ana_wiki_url = os.environ.get("ANA_WIKI_REPO", "")
    if ana_wiki_url:
        _clone_or_pull(ana_wiki_url, wiki_dir, ana_key_file)
    ana_ssh_cmd = (f"ssh -i {ana_key_file} -o StrictHostKeyChecking=accept-new"
                   if ana_key_file else None)
    wiki = WikiStore(wiki_dir, autocommit=True, ssh_cmd=ana_ssh_cmd)

    # --- Knowledge Wiki (Pesquisador) ---
    knowledge_dir = data_dir / "knowledge"
    knowledge_wiki_url = os.environ.get("KNOWLEDGE_WIKI_REPO", "")
    if knowledge_wiki_url:
        _clone_or_pull(knowledge_wiki_url, knowledge_dir, pesq_key_file)
    knowledge_wiki = WikiStore(knowledge_dir, autocommit=False)  # git_sync tool handles commits

    # --- LLM stack ---
    tracker = UsageTracker(store)
    cap_checker = CapChecker(tracker)

    # --- Load Ana ---
    ana_skill = parse_skill_file("agents/ana/SKILL.md")
    ana_tools = AnaTools(
        store=store,
        wiki=wiki,
        calendar=GoogleCalendarClient(),
    )

    # --- Agent registry (unified tool dispatch) ---
    registry = AgentRegistry()
    registry.register("ana", ana_tools)

    async def _ana_execute(name: str, args: dict) -> str:
        return await registry.execute_tool("ana", name, args)

    _ana_system_prompt = (
        f"{ana_skill.frontmatter.goal}\n\n"
        f"{ana_skill.body}\n\n"
        "## REGRA CRÍTICA: USE AS FERRAMENTAS\n\n"
        "Você tem acesso REAL ao Google Calendar, memória, todos e wiki do Leandro.\n"
        "NUNCA diga que fez algo sem ter chamado a ferramenta correspondente.\n"
        "- Para criar evento: CHAME calendar_create_event\n"
        "- Para ver agenda: CHAME calendar_list_events\n"
        "- Para salvar info: CHAME memory_set ou wiki_write\n"
        "- Para criar tarefa: CHAME todos_add\n\n"
        "Se o Leandro pedir para agendar algo, você DEVE chamar calendar_create_event "
        "com os dados corretos. Nunca responda 'pronto' sem ter executado a ferramenta."
    )
    _ana_runtime = build_runtime(
        "agents/ana/SKILL.md",
        tools_obj=ana_tools,
        execute_tool=_ana_execute,
        tracker=tracker,
        agent_name="ana",
        system_prompt=_ana_system_prompt,
        cap_exceeded_msg="Orçamento diário atingido. Volto amanhã cedinho.",
        fallback_msg="Não consegui completar a tarefa.",
        max_turns=6,
    )
    _ana_handler_cfg = _ana_runtime.handler_cfg
    ana_llm = _ana_handler_cfg.llm

    # --- Load Pesquisador ---
    pesq_skill = parse_skill_file("agents/pesquisador/SKILL.md")
    pesq_synthesis_cfg = LLMConfig(
        provider=pesq_skill.frontmatter.llm_synthesis.provider,
        model=pesq_skill.frontmatter.llm_synthesis.model,
        temperature=pesq_skill.frontmatter.llm_synthesis.temperature,
        fallback=[{"provider": pesq_skill.frontmatter.llm.provider,
                   "model": pesq_skill.frontmatter.llm.model}],
    )
    pesq_llm_synthesis = build_llm(pesq_synthesis_cfg, tracker, agent_name="pesquisador")
    pesq_tools = PesquisadorTools(wiki=knowledge_wiki, llm_synthesis=pesq_llm_synthesis)

    registry.register("pesquisador", pesq_tools)

    async def _pesq_execute(name: str, args: dict) -> str:
        return await registry.execute_tool("pesquisador", name, args)

    _pesq_system_prompt = (
        f"{pesq_skill.frontmatter.goal}\n\n"
        f"{pesq_skill.body}\n\n"
        "## PROTOCOLO OBRIGATÓRIO DE PESQUISA\n\n"
        "Quando o Leandro pedir para pesquisar um tema, você DEVE executar "
        "TODAS as etapas abaixo, sem pular nenhuma:\n\n"
        "1. wiki_search — verifica se já existe artigo na wiki\n"
        "2. Se não existe: web_search com pelo menos 3 queries diferentes "
        "(ex: '<tema> overview', '<tema> implementation guide', '<tema> best practices')\n"
        "3. web_fetch em pelo menos 3 URLs dos resultados (fontes técnicas e completas)\n"
        "4. raw_save para CADA fonte buscada — sem isso você não tem base para compilar\n"
        "5. compile_article — usa o LLM de síntese para criar o artigo profissional\n"
        "6. git_sync — persiste na wiki\n"
        "7. Responde ao Leandro com resumo do artigo criado\n\n"
        "NUNCA responda diretamente sem ter salvo fontes e chamado compile_article. "
        "Um artigo de Wikipedia sozinho não é suficiente — busque documentação oficial, "
        "RFC, guias técnicos, tutoriais de implementação. Profundidade técnica é obrigatória."
    )
    _pesq_runtime = build_runtime(
        "agents/pesquisador/SKILL.md",
        tools_obj=pesq_tools,
        execute_tool=_pesq_execute,
        tracker=tracker,
        agent_name="pesquisador",
        system_prompt=_pesq_system_prompt,
        cap_exceeded_msg="Orçamento diário atingido. Volto amanhã.",
        fallback_msg="Não consegui completar a pesquisa.",
        max_turns=20,
        progress_map={
            "web_search": "Pesquisando na web...",
            "web_fetch": "Lendo artigo...",
            "raw_save": "Salvando fonte...",
            "compile_article": "Compilando artigo com Gemini Pro...",
            "git_sync": "Publicando na wiki...",
        },
        result_max_chars=25000,
    )
    _pesq_handler_cfg = _pesq_runtime.handler_cfg
    pesq_llm = _pesq_handler_cfg.llm

    # --- Bot handlers (one-liner closures over per-agent configs) ---
    async def _handle_ana_message(body: str, _prefix: str, progress=None) -> str:
        return await handle_agent_message(_ana_handler_cfg, store, cap_checker, body, progress)

    async def _handle_pesquisador_message(body: str, _prefix: str, progress=None) -> str:
        return await handle_agent_message(_pesq_handler_cfg, store, cap_checker, body, progress)

    async def _handle_usage_cmd(args: str) -> str:
        from datetime import timedelta
        since_days = 30
        if "today" in args:
            since_days = 1
        elif "week" in args:
            since_days = 7
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
        lines = [f"📊 Uso últimos {since_days} dia(s)", ""]
        for agent in ("ana", "pesquisador"):
            total = tracker.total_usd(agent_name=agent, since=since)
            by_ctx = tracker.by_context(agent_name=agent, since=since)
            lines.append(f"{agent}:  US$ {total:.4f}")
            for ctx_name, cost in by_ctx.items():
                lines.append(f"  {ctx_name}: US$ {cost:.4f}")
        return "\n".join(lines)

    ana_token = os.environ["TELEGRAM_BOT_TOKEN"]
    pesq_token = os.environ["TELEGRAM_PESQ_BOT_TOKEN"]
    authorized_user_id = int(os.environ["AUTHORIZED_CHAT_ID"])
    group_chat_ids = [int(x) for x in os.environ.get("TELEGRAM_GROUP_CHAT_ID", "").split(",") if x.strip()]

    ana_bot = TelegramBot(
        token=ana_token,
        agent_name="ana",
        authorized_user_id=authorized_user_id,
        group_chat_ids=group_chat_ids,
        message_handler=_handle_ana_message,
        usage_command_handler=_handle_usage_cmd,
    )
    ana_app = ana_bot.build()

    pesq_bot = TelegramBot(
        token=pesq_token,
        agent_name="pesquisador",
        authorized_user_id=authorized_user_id,
        group_chat_ids=group_chat_ids,
        message_handler=_handle_pesquisador_message,
        usage_command_handler=_handle_usage_cmd,
    )
    pesq_app = pesq_bot.build()

    async def send_to_leandro(text: str) -> None:
        await ana_bot.send_message(text)

    async def send_pesq_to_leandro(text: str) -> None:
        await pesq_bot.send_message(text)

    # --- Scheduler ---
    scheduler = ConexusScheduler(store, tz="America/Sao_Paulo")
    scheduler.add_job(JobSpec("ana", "briefing",   "0 7 * * *",
                              make_briefing_job(ana_tools, ana_llm.acomplete, send_to_leandro)))
    scheduler.add_job(JobSpec("ana", "recap",      "0 21 * * *",
                              make_recap_job(ana_tools, ana_llm.acomplete, send_to_leandro)))
    scheduler.add_job(JobSpec("ana", "pre_event",  "*/5 * * * *",
                              make_pre_event_job(ana_tools, send_to_leandro)))
    scheduler.add_job(JobSpec("ana", "todo_sweep", "0 9-20 * * *",
                              make_todo_sweep_job(ana_tools, send_to_leandro)))
    scheduler.add_job(JobSpec("ana", "lint",       "0 22 * * 0",
                              make_lint_job(ana_tools, send_to_leandro)))
    scheduler.add_job(JobSpec("pesquisador", "weekly_digest", "0 20 * * 0",
                              make_weekly_digest_job(pesq_tools, pesq_llm.acomplete, store, send_pesq_to_leandro)))
    scheduler.add_job(JobSpec("pesquisador", "wiki_audit", "0 10 1 * *",
                              make_wiki_audit_job(pesq_tools, pesq_llm.acomplete, store, send_pesq_to_leandro)))
    scheduler.add_job(JobSpec("pesquisador", "proactive_research", "0 14 * * 3,6",
                              make_proactive_research_job(pesq_tools, pesq_llm.acomplete, pesq_llm_synthesis.acomplete, store, send_pesq_to_leandro)))

    # --- Start both bots ---
    await ana_app.initialize()
    await ana_bot.post_init()
    await ana_app.bot.delete_webhook(drop_pending_updates=True)
    await ana_app.start()
    await ana_app.updater.start_polling(drop_pending_updates=True)
    print(f"Ana online (@{ana_bot._bot_username}).", flush=True)

    await pesq_app.initialize()
    await pesq_bot.post_init()
    await pesq_app.bot.delete_webhook(drop_pending_updates=True)
    await pesq_app.start()
    await pesq_app.updater.start_polling(drop_pending_updates=True)
    print(f"Pesquisador online (@{pesq_bot._bot_username}).", flush=True)

    scheduler.start()
    await scheduler.catchup()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
        await ana_app.updater.stop()
        await ana_app.stop()
        await ana_app.shutdown()
        await pesq_app.updater.stop()
        await pesq_app.stop()
        await pesq_app.shutdown()
