"""Default memory-routing prompt (pt-BR) + override loader.

Auto-prepended to identity context when `identity.enabled`. Override via
SKILL.md `identity.prompt_override: ./custom.md`.
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_MEMORY_PROMPT_PT_BR = """\
Você possui memória persistente em três camadas:

1. **Facts** (memory_get/memory_set/memory_list_facts/memory_delete) — pares chave-valor atômicos.
   Use para preferências, IDs, datas, contatos. Curtos.

2. **Blocks** (block_get/block_set/block_list) — blocos de identidade com orçamento de caracteres.
   Use para persona, contexto do usuário, regras estáveis.

3. **Wiki** (wiki_*) — markdown narrativo por agente, versionado em git.
   Estrutura recomendada (padrão Karpathy):
   - `index.md` — catálogo de páginas; atualize via `wiki_index_update(path, summary)` após cada `wiki_write`.
   - `log.md` — registro cronológico; use `wiki_append_log(kind, title, body)`.
   - Páginas individuais em `topic.md` / `pasta/topico.md`.

Regras de escrita:
- Cada página tem frontmatter YAML automático (created, updated, tags, source, reviewed).
- Idioma do conteúdo segue o idioma da conversa (pt-BR por padrão).
- Ao citar uma página, use o formato `[caminho.md#ancora]` — ex: "Vide [arquitetura.md#wiki-layer]."
- Antes de escrever, busque com `wiki_search(query)` para evitar duplicação.
- Periodicamente, rode `wiki_lint()` para detectar órfãos, links quebrados, stubs.

Decida onde gravar:
- Fato curto e estruturado → memory_set.
- Contexto vivo de identidade → block_set.
- Conhecimento narrativo, decisões, notas → wiki_write + wiki_index_update.
"""


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

