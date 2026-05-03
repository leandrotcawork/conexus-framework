"""Assemble identity context block to prepend to system prompt.

Output format (markdown sections, in order):
  ## Block: user
  <block content>

  ## Block: <other blocks>

  ## Fatos recentes
  - key: value

  ## Wiki (índice)
  - path1
  - path2
"""
from __future__ import annotations

from conexus.core.config.skill_loader import IdentitySection
from conexus.core.identity.blocks import BlockStore
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


def assemble_identity_context(
    agent_id: str,
    cfg: IdentitySection,
    store: SqliteStore,
    wiki: WikiStore | None,
    blocks: BlockStore,
) -> str:
    if not cfg.enabled:
        return ""

    sections: list[str] = []

    # Blocks (in declaration order)
    for name in cfg.blocks:
        content = blocks.get(agent_id, name)
        if content:
            sections.append(f"## Block: {name}\n{content}")

    # Recent facts
    if cfg.facts.enabled and cfg.facts.inject_recent > 0:
        recent = store.facts_recent(agent_id, limit=cfg.facts.inject_recent)
        if recent:
            lines = [f"- {f['key']}: {f['value']}" for f in recent]
            sections.append("## Fatos recentes\n" + "\n".join(lines))

    # Wiki index
    if cfg.wiki and cfg.wiki.inject_index and wiki is not None:
        files = wiki.list("")
        if files:
            lines = [f"- {p}" for p in files]
            sections.append("## Wiki (índice)\n" + "\n".join(lines))

    return "\n\n".join(sections)
