"""Pesquisador's proactive jobs. Each builder returns an async JobFn closure.
Main.py wires everything together."""

from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from agents.pesquisador.tools import PesquisadorTools
from core.llm.context_tag import set_context
from core.llm.router import TrackedLLM
from core.memory.sqlite_store import SqliteStore

TZ = ZoneInfo("America/Sao_Paulo")


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
        print(f"[pesquisador:{kind}] failed: {e}", file=sys.stderr)


def make_weekly_digest_job(
    tools: PesquisadorTools,
    llm: TrackedLLM,
    store: SqliteStore,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    """Sunday 20:00 — summary of wiki additions/updates this week."""
    async def run() -> None:
        now = datetime.now(TZ)
        year, week, _ = now.isocalendar()
        ref_id = f"{year}-{week:02d}"

        async def body() -> str:
            # Read log.md for recent entries
            try:
                log_content = tools.wiki_read("log.md")
            except FileNotFoundError:
                log_content = "(nenhuma atividade)"

            # Count articles
            all_articles = tools.wiki_list("domains")
            entities = tools.wiki_list("entities")
            concepts = tools.wiki_list("concepts")

            prompt = (
                "Você é o Pesquisador. Escreva um resumo semanal curto em pt-BR "
                "do que foi adicionado/atualizado na wiki de conhecimento.\n\n"
                f"Semana: {ref_id}\n"
                f"Total artigos: domains={len(all_articles)}, "
                f"entities={len(entities)}, concepts={len(concepts)}\n\n"
                f"Log recente:\n{log_content[-2000:]}\n\n"
                "Formate como: 📚 Resumo semanal, seguido de bullet points."
            )

            with set_context("weekly_digest"):
                return await llm.acomplete([
                    {"role": "system", "content": "Você é o Pesquisador."},
                    {"role": "user", "content": prompt},
                ])

        await _run_with_ping_log(
            store, "weekly_digest", ref_id, "pesquisador", body, send_telegram
        )

    return run


def make_wiki_audit_job(
    tools: PesquisadorTools,
    llm: TrackedLLM,
    store: SqliteStore,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    """1st of month 10:00 — scan for low-confidence, stale, orphan articles."""
    async def run() -> None:
        now = datetime.now(TZ)
        ref_id = now.strftime("%Y-%m")

        async def body() -> str:
            all_files = tools.wiki_list("domains") + tools.wiki_list("entities") + tools.wiki_list("concepts")

            low_confidence: list[str] = []
            no_frontmatter: list[str] = []

            for f in all_files:
                try:
                    content = tools.wiki_read(f)
                    if "confidence: low" in content:
                        low_confidence.append(f)
                    if not content.startswith("---"):
                        no_frontmatter.append(f)
                except FileNotFoundError:
                    continue

            prompt = (
                "Você é o Pesquisador. Faça um relatório de auditoria curto em pt-BR.\n\n"
                f"Total artigos: {len(all_files)}\n"
                f"Artigos com confiança baixa ({len(low_confidence)}): {', '.join(low_confidence[:10])}\n"
                f"Artigos sem frontmatter ({len(no_frontmatter)}): {', '.join(no_frontmatter[:10])}\n\n"
                "Formate como: 🔍 Auditoria mensal, seguido de achados e recomendações."
            )

            with set_context("wiki_audit"):
                return await llm.acomplete([
                    {"role": "system", "content": "Você é o Pesquisador."},
                    {"role": "user", "content": prompt},
                ])

        await _run_with_ping_log(
            store, "wiki_audit", ref_id, "pesquisador", body, send_telegram
        )

    return run


def make_proactive_research_job(
    tools: PesquisadorTools,
    llm: TrackedLLM,
    llm_synthesis: TrackedLLM,
    store: SqliteStore,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    """Wed + Sat 14:00 — pick 1 topic and research using Tier 1 sources only."""
    async def run() -> None:
        now = datetime.now(TZ)
        ref_id = now.strftime("%Y-%m-%d")

        async def body() -> str:
            # Find low-confidence or empty domain articles to improve
            all_files = tools.wiki_list("domains")
            low_confidence: list[str] = []

            for f in all_files:
                try:
                    content = tools.wiki_read(f)
                    if "confidence: low" in content:
                        low_confidence.append(f)
                except FileNotFoundError:
                    continue

            if not low_confidence:
                return "📖 Pesquisa proativa: nenhum artigo com confiança baixa encontrado. Wiki está saudável!"

            target = low_confidence[0]

            # Read sources.md for trusted sources
            try:
                sources_config = tools.wiki_read("sources.md")
            except FileNotFoundError:
                sources_config = "(sem sources.md configurado)"

            # Read the current article
            current_content = tools.wiki_read(target)

            # Search for more information
            topic = target.split("/")[-1].replace(".md", "").replace("-", " ")
            search_results = tools.web_search(topic, max_results=5, tier=1)  # Tier 1 ONLY for proactive
            search_text = "\n".join(
                f"- {r['title']}: {r['snippet']}" for r in search_results
            )

            # Use R1 for synthesis
            prompt = (
                f"Você é o Pesquisador. Melhore o artigo '{target}' da wiki.\n\n"
                f"Fontes confiáveis:\n{sources_config[:1000]}\n\n"
                f"Artigo atual:\n{current_content[:2000]}\n\n"
                f"Resultados de pesquisa:\n{search_text}\n\n"
                "Reescreva o artigo completo com frontmatter YAML (domain, confidence, sources, last_updated). "
                "Melhore a qualidade e aumente a confiança. Mantenha formato Wikipedia: "
                "estruturado, factual, denso. Inclua ## See Also e ## Sources."
            )

            with set_context("proactive_research"):
                improved = await llm_synthesis.acomplete([
                    {"role": "system", "content": "Você é um pesquisador técnico especializado."},
                    {"role": "user", "content": prompt},
                ])

            tools.wiki_write(target, improved)
            tools.wiki.append_log("proactive", f"Improved {target}", f"Upgraded via proactive research")
            tools.git_sync(f"proactive: improve {target}")

            return f"📖 Pesquisa proativa: artigo melhorado — {target}"

        await _run_with_ping_log(
            store, "proactive_research", ref_id, "pesquisador", body, send_telegram
        )

    return run