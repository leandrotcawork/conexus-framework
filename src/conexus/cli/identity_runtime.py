"""Wire identity config from SKILL.md into runtime components."""
from __future__ import annotations

from pathlib import Path

from conexus.core.config.skill_loader import IdentitySection, WikiSection
from conexus.core.identity.blocks import BlockStore
from conexus.core.identity.tools import IdentityTools
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


class IdentityRuntime:
    """Holds the identity components built once per agent."""

    def __init__(
        self,
        agent_id: str,
        cfg: IdentitySection,
        store: SqliteStore,
        skill_dir: Path,
    ):
        self.agent_id = agent_id
        self.cfg = cfg
        self.store = store
        self.skill_dir = skill_dir
        self.blocks = BlockStore(store)
        self.wiki: WikiStore | None = None
        if cfg.wiki:
            self.wiki = _build_wiki(cfg.wiki, skill_dir)
        block_specs = {name: spec.budget_chars for name, spec in cfg.blocks.items()}
        # Seed initial block content if not yet present
        for name, spec in cfg.blocks.items():
            if spec.initial and self.blocks.get(agent_id, name) is None:
                self.blocks.set(agent_id, name, spec.initial, spec.budget_chars)
        self.tools = IdentityTools(
            agent_id=agent_id,
            store=store,
            wiki=self.wiki,
            blocks=self.blocks,
            block_specs=block_specs,
        )


def _build_wiki(wiki_cfg: WikiSection, skill_dir: Path) -> WikiStore:
    if wiki_cfg.backend == "local":
        wiki_path = (
            skill_dir / wiki_cfg.dir
            if not Path(wiki_cfg.dir).is_absolute()
            else Path(wiki_cfg.dir)
        )
        return WikiStore.local(wiki_path)
    if wiki_cfg.backend == "github_app":
        raise NotImplementedError(
            "github_app backend lands in Phase 2 — use 'local' for now"
        )
    raise ValueError(f"unknown wiki backend: {wiki_cfg.backend!r}")


def build_identity_runtime(
    agent_id: str,
    cfg: IdentitySection | None,
    store: SqliteStore,
    skill_dir: Path,
) -> IdentityRuntime | None:
    """Return an IdentityRuntime when identity.enabled, else None."""
    if cfg is None or not cfg.enabled:
        return None
    return IdentityRuntime(agent_id, cfg, store, skill_dir)
