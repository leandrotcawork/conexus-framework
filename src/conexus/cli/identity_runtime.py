"""Wire identity config from SKILL.md into runtime components."""
from __future__ import annotations

from pathlib import Path

from conexus.core.config.skill_loader import IdentitySection, WikiSection
from conexus.core.identity.blocks import BlockStore
from conexus.core.identity.tools import IdentityTools
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki import LocalBackend
from conexus.core.memory.wiki.index_sqlite import SqliteFtsIndex
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
            self.wiki = _build_wiki(cfg.wiki, skill_dir, agent_id=agent_id, store=store)
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


def _build_wiki(
    wiki_cfg: WikiSection,
    skill_dir: Path,
    *,
    agent_id: str = "",
    store: SqliteStore | None = None,
) -> WikiStore:
    if wiki_cfg.backend == "local":
        backend = LocalBackend(skill_dir / wiki_cfg.dir)
        idx = SqliteFtsIndex(store=store, agent_id=agent_id, backend=backend) if store and agent_id else None
        return WikiStore(backend, index=idx)
    if wiki_cfg.backend == "github_app":
        if store is None or not agent_id:
            raise RuntimeError("github_app backend requires store + agent_id")
        row = store.github_app_install_get(agent_id)
        if row is None:
            raise RuntimeError(
                f"Agent '{agent_id}' github wiki not connected. "
                "Visit /admin/oauth/github/start to install the app."
            )
        import os

        from conexus.core.memory.wiki.github_app import GitHubAppBackend

        backend = GitHubAppBackend(
            local_root=skill_dir / wiki_cfg.dir,
            repo_slug=row["repo_slug"],
            installation_id=row["installation_id"],
            app_id=os.environ["GITHUB_APP_ID"],
            private_key_pem=os.environ["GITHUB_APP_PRIVATE_KEY"],
        )
        idx = SqliteFtsIndex(store=store, agent_id=agent_id, backend=backend)
        return WikiStore(backend, index=idx)
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
