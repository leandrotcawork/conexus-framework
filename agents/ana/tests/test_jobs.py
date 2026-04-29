from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from agents.ana.jobs import (
    make_briefing_job,
    make_pre_event_job,
    make_todo_sweep_job,
)
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki_store import WikiStore


class _Tools:
    def __init__(self, store: SqliteStore, wiki: WikiStore, calendar: MagicMock):
        self.store = store
        self.wiki = wiki
        self.calendar = calendar

    def calendar_list_events(self, start_iso: str, end_iso: str) -> list[dict]:
        return self.calendar.list_events(start_iso, end_iso)

    def todos_list(self, status: str = "open") -> list[dict]:
        return self.store.todos_list(status)

    def memory_list_facts(self) -> list[dict]:
        return self.store.facts_list()

    def wiki_append_log(self, kind: str, title: str, body: str) -> dict:
        self.wiki.append_log(kind, title, body)
        return {"ok": True}


def _make_tools(tmp_db_path: Path, tmp_wiki_dir: Path) -> Any:
    store = SqliteStore(tmp_db_path)
    store.init_db()
    wiki = WikiStore(tmp_wiki_dir, autocommit=False)
    return _Tools(store=store, wiki=wiki, calendar=MagicMock())


def _mock_llm(response: str = "Bom dia!") -> AsyncMock:
    return AsyncMock(return_value=response)


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
