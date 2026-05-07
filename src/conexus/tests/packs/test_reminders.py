from pathlib import Path
import importlib.util
import sys
import pytest
from conexus.core.memory.sqlite_store import SqliteStore


def _load_reminders(repo_root: Path):
    p = repo_root / "packs" / "reminders" / "tools.py"
    spec = importlib.util.spec_from_file_location("_pack_reminders", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_pack_reminders"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def reminders(tmp_path):
    repo_root = Path(__file__).parents[4]
    db_path = tmp_path / "db.sqlite"
    store = SqliteStore(db_path)
    store.init_db()
    store.apply_pack_migrations("reminders", repo_root / "packs" / "reminders" / "migrations")
    mod = _load_reminders(repo_root)
    return mod.ReminderTools(store=store, agent_name="ana")


def test_set_reminder_returns_id(reminders):
    rid = reminders.set_reminder(when_cron="0 9 * * *", message="standup")
    assert isinstance(rid, int)
    assert rid > 0


def test_list_reminders_returns_active(reminders):
    reminders.set_reminder(when_cron="0 9 * * *", message="m1")
    reminders.set_reminder(when_cron="0 10 * * *", message="m2")
    items = reminders.list_reminders()
    assert len(items) == 2
    assert {i["message"] for i in items} == {"m1", "m2"}


def test_cancel_reminder_marks_inactive(reminders):
    rid = reminders.set_reminder(when_cron="0 9 * * *", message="x")
    assert reminders.cancel_reminder(rid) is True
    assert reminders.list_reminders() == []


def test_cancel_unknown_returns_false(reminders):
    assert reminders.cancel_reminder(99999) is False
