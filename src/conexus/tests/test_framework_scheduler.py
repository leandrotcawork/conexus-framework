from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.scheduler.scheduler import ConexusScheduler, JobSpec, current_ref_id


def _setup(tmp_db_path):
    store = SqliteStore(tmp_db_path)
    store.init_db()
    return ConexusScheduler(store, tz="America/Sao_Paulo"), store


def test_current_ref_id_briefing():
    local = datetime(2026, 4, 12, 7, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert current_ref_id("briefing", local) == "2026-04-12"


def test_current_ref_id_lint_uses_iso_week():
    local = datetime(2026, 4, 12, 22, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    # 2026-04-12 is a Sunday in ISO week 15
    assert current_ref_id("lint", local) == "2026-15"


@pytest.mark.asyncio
async def test_catchup_runs_missed_briefing(tmp_db_path):
    sched, store = _setup(tmp_db_path)
    fired = []

    async def run():
        fired.append(1)

    spec = JobSpec(agent_name="ana", kind="briefing", cron="0 7 * * *", fn=run)
    sched.add_job(spec)

    # Simulate 09:00 — within the catchup window (< 12:00), briefing not yet sent
    with freeze_time("2026-04-12 12:00:00+00:00"):  # 09:00 BRT
        await sched.catchup()

    assert len(fired) == 1


@pytest.mark.asyncio
async def test_catchup_skips_if_already_sent(tmp_db_path):
    sched, store = _setup(tmp_db_path)
    fired = []

    async def run():
        fired.append(1)

    spec = JobSpec(agent_name="ana", kind="briefing", cron="0 7 * * *", fn=run)
    sched.add_job(spec)

    # Mark it already sent
    store.ping_mark_sent("briefing", "2026-04-12", "ana")

    with freeze_time("2026-04-12 12:00:00+00:00"):  # 09:00 BRT
        await sched.catchup()

    assert len(fired) == 0


@pytest.mark.asyncio
async def test_catchup_skips_after_window(tmp_db_path):
    sched, store = _setup(tmp_db_path)
    fired = []

    async def run():
        fired.append(1)

    spec = JobSpec(agent_name="ana", kind="briefing", cron="0 7 * * *", fn=run)
    sched.add_job(spec)

    # 15:00 BRT = 18:00 UTC — past the 12:00 catchup window for briefing
    with freeze_time("2026-04-12 18:00:00+00:00"):
        await sched.catchup()

    assert len(fired) == 0
