"""Seed Ana's wiki on the Fly.io volume. Run via: fly ssh console -C 'python3 /app/scripts/seed_wiki.py'"""
import pathlib

base = pathlib.Path("/data/wiki")
(base / "about").mkdir(parents=True, exist_ok=True)
(base / "preferences").mkdir(exist_ok=True)
(base / "projects").mkdir(exist_ok=True)
(base / "people").mkdir(exist_ok=True)
(base / "procedures").mkdir(exist_ok=True)

(base / "log.md").write_text("# Log da Ana\n")

(base / "index.md").write_text(
    "# Wiki da Ana — Índice\n\n"
    "## About\n"
    "- [conexus](about/conexus.md) — o framework pessoal do Leandro\n\n"
    "## Preferences\n"
    "*(vazio — Ana preenche conforme aprende)*\n\n"
    "## Projects\n"
    "*(vazio)*\n\n"
    "## People\n"
    "*(vazio)*\n\n"
    "## Procedures\n"
    "*(vazio)*\n"
)

(base / "about" / "conexus.md").write_text(
    "# Conexus (também escrito Co-Nexus)\n\n"
    "Framework pessoal de agentes do Leandro Theodoro. "
    "Ana é a primeira agente (secretária executiva). "
    "Próximos agentes planejados: Researcher (pesquisa e notícias) e Code Manager (análise de código).\n\n"
    "Todos os agentes compartilham a mesma infraestrutura: "
    "LLM router (LiteLLM), memória SQLite, bot Telegram, scheduler APScheduler.\n\n"
    "Repositório: privado. Deploy: Fly.io, região gru (São Paulo).\n"
)

print("Wiki seed OK")
for f in sorted(base.rglob("*")):
    print(f" {f.relative_to(base)}")
