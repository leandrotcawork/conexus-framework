"""APScheduler wrapper with catchup for missed ticks.

Each agent registers its scheduled jobs via `add_job`. On startup, `catchup()`
runs any catchable jobs whose expected ref_id is missing from ping_log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from conexus.core.memory.sqlite_store import SqliteStore


JobFn = Callable[[], Awaitable[None]]


@dataclass
class JobSpec:
    agent_name: str
    kind: str
    cron: str
    fn: JobFn


CATCHUP_WINDOWS = {
    # kind -> (catchable, end_hour_local)  end_hour == 0 means "end of day"
    # Ana
    "briefing":            (True,  12),
    "recap":               (True,  24),
    "pre_event":           (False, 0),
    "todo_sweep":          (False, 0),
    "lint":                (True,  0),
    # Pesquisador
    "weekly_digest":       (True,  0),   # weekly, catchable
    "wiki_audit":          (True,  0),   # monthly, catchable
    "proactive_research":  (False, 0),   # skip if missed
    # Reminders pack
    "reminder":            (False, 0),
}


def current_ref_id(kind: str, now_local: datetime) -> str:
    if kind in ("briefing", "recap", "todo_sweep", "proactive_research"):
        return now_local.strftime("%Y-%m-%d")
    if kind in ("lint", "weekly_digest"):
        year, week, _ = now_local.isocalendar()
        return f"{year}-{week:02d}"
    if kind == "wiki_audit":
        return now_local.strftime("%Y-%m")
    if kind == "pre_event":
        return ""
    return ""


class ConexusScheduler:
    def __init__(self, store: SqliteStore, tz: str = "America/Sao_Paulo"):
        self.store = store
        self.tz = ZoneInfo(tz)
        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self.jobs: list[JobSpec] = []

    def add_job(self, spec: JobSpec) -> None:
        self.jobs.append(spec)
        self.scheduler.add_job(
            spec.fn,
            CronTrigger.from_crontab(spec.cron, timezone=self.tz),
            id=f"{spec.agent_name}:{spec.kind}",
            replace_existing=True,
        )

    async def catchup(self) -> None:
        """On startup, run any catchable jobs that didn't fire today/this week."""
        now_local = datetime.now(self.tz)
        for spec in self.jobs:
            catchable, end_hour = CATCHUP_WINDOWS.get(spec.kind, (False, 0))
            if not catchable:
                continue
            ref = current_ref_id(spec.kind, now_local)
            if not ref:
                continue
            if self.store.ping_was_sent(spec.kind, ref, spec.agent_name):
                continue
            if end_hour and now_local.hour >= end_hour:
                continue
            await spec.fn()

    def start(self) -> None:
        self.scheduler.start()

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)


def rehydrate_reminders(
    sched: ConexusScheduler,
    store: SqliteStore,
    *,
    dispatch,
) -> None:
    """Read active reminders from sqlite and register one job per row.

    Call this at bot startup after ConexusScheduler is built and before sched.start().
    dispatch: async callable (message: str) -> None — typically the agent's send_text fn.
    """
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT id, agent_name, cron, message FROM pack_reminders_jobs WHERE active=1"
        ).fetchall()
    for row in rows:
        msg = row["message"]

        async def fn(_msg=msg):
            await dispatch(_msg)

        sched.add_job(JobSpec(
            agent_name=row["agent_name"],
            kind="reminder",
            cron=row["cron"],
            fn=fn,
        ))
