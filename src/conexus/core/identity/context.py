"""Assemble identity context block to prepend to system prompt."""
from __future__ import annotations

from pathlib import Path

from conexus.core.config.skill_loader import IdentitySection
from conexus.core.identity.blocks import BlockStore
from conexus.core.identity.prompt import load_memory_prompt
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


def assemble_identity_context(
    agent_id: str,
    cfg: IdentitySection,
    store: SqliteStore,
    wiki: WikiStore | None,
    blocks: BlockStore,
    skill_dir: Path | None = None,
) -> str:
    if not cfg.enabled:
        return ""

    sections: list[str] = [load_memory_prompt(cfg.prompt_override, skill_dir)]

    for name in cfg.blocks:
        content = blocks.get(agent_id, name)
        if content:
            sections.append(f"## Block: {name}\n{content}")

    if cfg.facts.enabled and cfg.facts.inject_recent > 0:
        recent = store.facts_recent(agent_id, limit=cfg.facts.inject_recent)
        if recent:
            lines = [f"- {f['key']}: {f['value']}" for f in recent]
            sections.append("## Fatos recentes\n" + "\n".join(lines))

    if cfg.wiki and cfg.wiki.inject_index and wiki is not None:
        files = wiki.list("")
        if files:
            lines = [f"- {p}" for p in files]
            sections.append("## Wiki (índice)\n" + "\n".join(lines))

    return "\n\n".join(sections)
