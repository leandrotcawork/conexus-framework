"""Deterministic replay of a frozen audit session against a (possibly changed) registry."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from conexus.core.team.handoff import Handoff
from conexus.core.team.handoff_router import HandoffRouter
from conexus.core.team.team_registry import TeamRegistry


@dataclass
class ReplayMismatch:
    kind: str        # "route" | "missing_member"
    expected: Any
    actual: Any
    detail: str = ""


@dataclass
class ReplayReport:
    handoffs_replayed: int = 0
    tools_replayed: int = 0
    mismatches: list[ReplayMismatch] = field(default_factory=list)


def replay_session(
    conn: sqlite3.Connection, *, session_id: str, registry: TeamRegistry
) -> ReplayReport:
    report = ReplayReport()
    router = HandoffRouter(registry)

    rows = conn.execute(
        "SELECT from_agent, to_agent, payload_json FROM handoff_audit "
        "WHERE session_id=? ORDER BY id",
        (session_id,),
    ).fetchall()

    for from_agent, recorded_to, payload_json in rows:
        report.handoffs_replayed += 1
        try:
            payload = json.loads(payload_json)
        except (json.JSONDecodeError, TypeError):
            payload = {}
        h = Handoff(from_agent=from_agent, to_agent=recorded_to, payload=payload)
        try:
            resolved = router._resolve(h)
        except ValueError as exc:
            report.mismatches.append(
                ReplayMismatch(kind="route", expected=recorded_to, actual=None, detail=str(exc))
            )
            continue
        if resolved != recorded_to:
            report.mismatches.append(
                ReplayMismatch(kind="route", expected=recorded_to, actual=resolved)
            )

    tool_count = conn.execute(
        "SELECT COUNT(*) FROM tool_audit WHERE session_id=?", (session_id,)
    ).fetchone()
    report.tools_replayed = tool_count[0] if tool_count else 0

    return report
