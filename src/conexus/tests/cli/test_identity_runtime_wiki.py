from pathlib import Path

from conexus.cli.identity_runtime import _build_wiki
from conexus.core.config.skill_loader import WikiSection
from conexus.core.memory.sqlite_store import SqliteStore
from conexus.core.memory.wiki.index import WikiIndex


def test_build_wiki_local_attaches_index(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db")); store.init_db()
    skill_dir = tmp_path / "agent"
    skill_dir.mkdir()
    cfg = WikiSection(backend="local", dir="wiki", inject_index=False)
    ws = _build_wiki(cfg, skill_dir, agent_id="a", store=store)
    assert ws.index is not None
    assert isinstance(ws.index, WikiIndex)


def test_build_wiki_search_works_round_trip(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db")); store.init_db()
    skill_dir = tmp_path / "agent"
    skill_dir.mkdir()
    cfg = WikiSection(backend="local", dir="wiki", inject_index=False)
    ws = _build_wiki(cfg, skill_dir, agent_id="a", store=store)
    ws.write("a.md", "# A\nalpha beta")
    hits = ws.search("alpha")
    assert hits and hits[0]["path"] == "a.md"
