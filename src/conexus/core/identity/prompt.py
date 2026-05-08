"""Default memory-routing prompt (pt-BR) + override loader.

Auto-prepended to identity context when `identity.enabled`. Override via
SKILL.md `identity.prompt_override: ./custom.md`.
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_MEMORY_PROMPT_PT_BR = """\
## Memória

Você tem três sistemas de memória:

1. **Fatos** (`memory_set`) — informações atômicas e permanentes sobre o usuário:
   nome, família, preferências, datas importantes, idioma. Use chave em snake_case.
   Exemplos: nome="Leandro", mae="Maria", filha="Ana", cor_favorita="azul".

2. **Wiki** (`wiki_write`) — conteúdo narrativo, projetos, resumos, logs de pesquisa.
   Use quando a informação tem mais de uma frase ou precisa de estrutura.

3. **Notas** (pacote `notes`) — listas efêmeras, lembretes curtos, rascunhos.
   Use só quando o usuário pedir explicitamente "anote" ou "faça uma lista".

Regra: se o usuário compartilha algo sobre quem ele é ou quem está na vida dele,
SEMPRE use `memory_set`. Notas são para tarefas, não para identidade."""


def load_memory_prompt(override: str | None, skill_dir: Path | None) -> str:
    """Return override content if set, else default. Resolves override relative to skill_dir."""
    if not override:
        return DEFAULT_MEMORY_PROMPT_PT_BR
    p = Path(override)
    if not p.is_absolute() and skill_dir is not None:
        p = skill_dir / p
    if not p.exists():
        raise FileNotFoundError(
            f"identity.prompt_override not found: {p}. "
            "Check the path in SKILL.md."
        )
    return p.read_text(encoding="utf-8")
