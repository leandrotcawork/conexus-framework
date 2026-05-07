from pathlib import Path
import importlib.util, sys
import pytest
from conexus.core.memory.sqlite_store import SqliteStore


@pytest.fixture
def notes(tmp_path):
    repo_root = Path(__file__).parents[4]
    store = SqliteStore(tmp_path / "db.sqlite")
    store.init_db()
    store.apply_pack_migrations("notes", repo_root / "packs" / "notes" / "migrations")
    p = repo_root / "packs" / "notes" / "tools.py"
    spec = importlib.util.spec_from_file_location("_pack_notes", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_pack_notes"] = mod
    spec.loader.exec_module(mod)
    return mod.NoteTools(store=store, agent_name="ana")


def test_add_note(notes):
    nid = notes.add_note(text="remember to ship")
    assert nid > 0


def test_list_notes_recent_first(notes):
    notes.add_note("first")
    notes.add_note("second")
    items = notes.list_notes()
    assert [i["text"] for i in items] == ["second", "first"]


def test_search_notes(notes):
    notes.add_note("cron expression hint")
    notes.add_note("unrelated")
    items = notes.search_notes("cron")
    assert len(items) == 1
    assert "cron" in items[0]["text"]
