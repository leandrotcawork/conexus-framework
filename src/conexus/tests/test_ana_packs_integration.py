from pathlib import Path
import pytest
from conexus.core.agent_registry import AgentRegistry
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.skills.skill_resolver import SkillLoader


def test_loader_registers_reminders_and_notes(tmp_path: Path):
    repo_root = Path(__file__).parents[3]
    store = SqliteStore(tmp_path / "db.sqlite")
    store.init_db()
    for pack in ("reminders", "notes"):
        store.apply_pack_migrations(pack, repo_root / "packs" / pack / "migrations")

    agent_dir = tmp_path / "agents" / "ana"
    agent_dir.mkdir(parents=True)
    registry = AgentRegistry()
    loader = SkillLoader(
        agent_dir, registry, "ana",
        packs_root=repo_root / "packs",
        pack_ctx={"store": store, "agent_name": "ana"},
    )
    loader.load(["reminders", "notes"])

    all_tools: set[str] = set()
    for backend in registry._backends.get("ana", []):
        all_tools.update(backend.list_tools())

    assert {"set_reminder", "list_reminders", "cancel_reminder"} <= all_tools
    assert {"add_note", "list_notes", "search_notes"} <= all_tools
