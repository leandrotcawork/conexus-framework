"""IdentityRuntime dispatches wiki construction by backend field."""
from __future__ import annotations

from pathlib import Path

import pytest

from conexus.core.config.skill_loader import IdentitySection, WikiSection
from conexus.core.memory.sqlite_store import SqliteStore


def _store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(str(tmp_path / "db.sqlite"))


def test_local_backend_creates_wikistore(tmp_path):
    from conexus.cli.identity_runtime import build_identity_runtime
    cfg = IdentitySection(enabled=True, wiki=WikiSection(backend="local", dir="./wiki"))
    rt = build_identity_runtime("a", cfg, _store(tmp_path), tmp_path)
    assert rt is not None
    assert rt.wiki is not None
    assert rt.skill_dir == tmp_path
    rt.wiki.write("x.md", "hi")
    assert (tmp_path / "wiki" / "x.md").read_text(encoding="utf-8") == "hi"


def test_github_app_backend_raises_not_implemented(tmp_path):
    from conexus.cli.identity_runtime import build_identity_runtime
    cfg = IdentitySection(enabled=True, wiki=WikiSection(backend="github_app", dir="./wiki"))
    with pytest.raises(NotImplementedError):
        build_identity_runtime("a", cfg, _store(tmp_path), tmp_path)


def test_no_wiki_block_yields_no_wiki(tmp_path):
    """Explicit `wiki: null` in YAML disables wiki entirely."""
    from conexus.cli.identity_runtime import build_identity_runtime
    cfg = IdentitySection(enabled=True, wiki=None)
    rt = build_identity_runtime("a", cfg, _store(tmp_path), tmp_path)
    assert rt is not None
    assert rt.wiki is None
    assert rt.skill_dir == tmp_path
