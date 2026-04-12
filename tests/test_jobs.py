import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from agents.ana.jobs import (
    make_briefing_job,
    make_lint_job,
    make_pre_event_job,
    make_recap_job,
    make_todo_sweep_job,
)
from agents.ana.tools import AnaTools
from core.memory.sqlite_store import SqliteStore
from core.memory.wiki_store import WikiStore


def _make_tools(tmp_db_path: Path, tmp_wiki_dir: Path) -> AnaTools:
    store = SqliteStore(tmp_db_path)
    store.init_db()
    wiki = WikiStore(tmp_wiki_dir, autocommit=False)
    return AnaTools(store=store, wiki=wiki, calendar=MagicMock())


def _mock_llm(response: str = "Bom dia!") -> MagicMock:
    llm = MagicMock()
    llm.complete.return_value = response
    return llm


@pytest.mark.asyncio
async def test_briefing_sends_message(tmp_db_path, tmp_wiki_dir):
    tools = _make_tools(tmp_db_path, tmp_wiki_dir)
    tools.calendar.list_events.return_value = []
    llm = _mock_llm("Bom dia, Leandro!")
    sent = []

    async def send(text): sent.append(text)

    job = make_briefing_job(tools, llm, send)
    with freeze_time("2026-04-12 10:00:00"):
        await job()

    assert len(sent) == 1
    assert "Bom dia" in sent[0]
    assert tools.store.ping_was_sent("briefing", "2026-04-12", "ana")


@pytest.mark.asyncio
async def test_briefing_is_idempotent(tmp_db_path, tmp_wiki_dir):
    tools = _make_tools(tmp_db_path, tmp_wiki_dir)
    tools.calendar.list_events.return_value = []
    llm = _mock_llm("Bom dia!")
    sent = []

    async def send(text): sent.append(text)

    tools.store.ping_mark_sent("briefing", "2026-04-12", "ana")
    job = make_briefing_job(tools, llm, send)
    with freeze_time("2026-04-12 10:00:00"):
        await job()

    assert len(sent) == 0


@pytest.mark.asyncio
async def test_pre_event_sends_per_event(tmp_db_path, tmp_wiki_dir):
    tools = _make_tools(tmp_db_path, tmp_wiki_dir)
    tools.calendar.list_events.return_value = [
        {"id": "e1", "title": "Reunião", "start": "2026-04-12T10:15:00-03:00"},
    ]
    sent = []

    async def send(text): sent.append(text)

    job = make_pre_event_job(tools, send)
    with freeze_time("2026-04-12 10:00:00"):
        await job()

    assert len(sent) == 1
    assert "Reunião" in sent[0]
    assert tools.store.ping_was_sent("pre_event", "e1", "ana")


@pytest.mark.asyncio
async def test_todo_sweep_sends_only_overdue(tmp_db_path, tmp_wiki_dir):
    tools = _make_tools(tmp_db_path, tmp_wiki_dir)
    # Add an overdue todo (past due date)
    tools.store.todo_add("comprar café", due_iso="2026-04-11T10:00:00-03:00")
    tools.store.todo_add("tarefa futura", due_iso="2026-04-15T10:00:00-03:00")
    sent = []

    async def send(text): sent.append(text)

    job = make_todo_sweep_job(tools, send)
    with freeze_time("2026-04-12 14:00:00"):
        await job()

    assert len(sent) == 1
    assert "comprar café" in sent[0]
    assert "tarefa futura" not in sent[0]
