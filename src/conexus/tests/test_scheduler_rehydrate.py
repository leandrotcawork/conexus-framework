from pathlib import Path
import pytest
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.scheduler.scheduler import ConexusScheduler, rehydrate_reminders


@pytest.mark.asyncio
async def test_rehydrate_loads_active_jobs(tmp_path: Path):
    repo_root = Path(__file__).parents[3]
    store = SqliteStore(tmp_path / "db.sqlite")
    store.init_db()
    store.apply_pack_migrations("reminders", repo_root / "packs" / "reminders" / "migrations")
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO pack_reminders_jobs (agent_name, cron, message, created_at)"
            " VALUES ('ana','0 9 * * *','m1', datetime('now'))"
        )
        conn.execute(
            "INSERT INTO pack_reminders_jobs (agent_name, cron, message, active, created_at)"
            " VALUES ('ana','0 10 * * *','m2', 0, datetime('now'))"
        )
        conn.commit()

    fired: list[str] = []

    async def fire(message: str) -> None:
        fired.append(message)

    sched = ConexusScheduler(store)
    rehydrate_reminders(sched, store, dispatch=fire)
    assert len([j for j in sched.jobs if j.kind == "reminder"]) == 1
