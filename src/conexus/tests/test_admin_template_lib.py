from pathlib import Path

import pytest

from conexus.web.admin.services.template_lib import TEMPLATES, scaffold_agent


def test_chat_only_creates_files(tmp_path: Path) -> None:
    scaffold_agent(tmp_path, "ana", template="chat-only")
    d = tmp_path / "ana"
    assert (d / "SKILL.md").exists()
    assert (d / "tools.py").exists()
    assert (d / "__init__.py").exists()


def test_invalid_name_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        scaffold_agent(tmp_path, "Bad-Name", template="chat-only")
    with pytest.raises(ValueError):
        scaffold_agent(tmp_path, "../etc/passwd", template="chat-only")


def test_existing_agent_rejected(tmp_path: Path) -> None:
    scaffold_agent(tmp_path, "ana", template="chat-only")
    with pytest.raises(FileExistsError):
        scaffold_agent(tmp_path, "ana", template="chat-only")


def test_chat_memory_gcal_includes_connector(tmp_path: Path) -> None:
    scaffold_agent(tmp_path, "ana", template="chat+memory+gcal")
    pack = tmp_path / "ana" / "skills" / "google_calendar"
    assert (pack / "SKILL_PACK.md").exists()
    assert (pack / "connector.json").exists()


def test_template_list() -> None:
    assert set(TEMPLATES) == {"chat-only", "chat+memory", "chat+memory+gcal"}
