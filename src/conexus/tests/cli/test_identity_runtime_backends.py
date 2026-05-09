"""IdentityRuntime dispatches wiki construction by backend field."""
from __future__ import annotations

from pathlib import Path

from conexus.core.config.skill_loader import IdentitySection, WikiSection
from conexus.core.memory.sqlite_store import SqliteStore


def _store(tmp_path: Path) -> SqliteStore:
    s = SqliteStore(str(tmp_path / "db.sqlite"))
    s.init_db()
    return s


def test_local_backend_creates_wikistore(tmp_path):
    from conexus.cli.identity_runtime import build_identity_runtime
    cfg = IdentitySection(enabled=True, wiki=WikiSection(backend="local", dir="./wiki"))
    rt = build_identity_runtime("a", cfg, _store(tmp_path), tmp_path)
    assert rt is not None
    assert rt.wiki is not None
    assert rt.skill_dir == tmp_path
    rt.wiki.write("x.md", "hi")
    content = (tmp_path / "wiki" / "x.md").read_text(encoding="utf-8")
    assert "hi" in content


def test_github_app_backend_builds_from_store(tmp_path):
    """When store has install row and env vars are set, backend builds successfully."""
    from unittest.mock import patch

    from conexus.cli.identity_runtime import _build_wiki
    from conexus.core.config.skill_loader import WikiSection
    from conexus.core.memory.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "test.db"))
    store.init_db()
    store.github_app_install_set("myagent", "owner/repo", 99)

    wiki_cfg = WikiSection(backend="github_app", repo="owner/repo")

    with patch("conexus.core.memory.wiki.github_app.GitHubAppBackend._ensure_clone"), \
         patch.dict("os.environ", {"GITHUB_APP_ID": "123", "GITHUB_APP_PRIVATE_KEY": "pem"}):
        ws = _build_wiki(wiki_cfg, tmp_path, agent_id="myagent", store=store)

    assert ws is not None


def test_github_app_backend_missing_install_raises(tmp_path):
    import pytest

    from conexus.cli.identity_runtime import _build_wiki
    from conexus.core.config.skill_loader import WikiSection
    from conexus.core.memory.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "test.db"))
    store.init_db()
    wiki_cfg = WikiSection(backend="github_app", repo="owner/repo")

    with pytest.raises(RuntimeError, match="not connected"):
        _build_wiki(wiki_cfg, tmp_path, agent_id="myagent", store=store)


def test_no_wiki_block_yields_no_wiki(tmp_path):
    """Explicit `wiki: null` in YAML disables wiki entirely."""
    from conexus.cli.identity_runtime import build_identity_runtime
    cfg = IdentitySection(enabled=True, wiki=None)
    rt = build_identity_runtime("a", cfg, _store(tmp_path), tmp_path)
    assert rt is not None
    assert rt.wiki is None
    assert rt.skill_dir == tmp_path
