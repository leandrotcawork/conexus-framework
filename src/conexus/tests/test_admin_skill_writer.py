from pathlib import Path

import yaml

from conexus.web.admin.services.skill_writer import write_skill_md


def test_write_creates_round_trippable_yaml(tmp_path: Path) -> None:
    fm = {"name": "ana", "role": "test", "goal": "x",
          "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.4},
          "tools": ["foo"]}
    body = "system prompt\nline 2"
    out = tmp_path / "SKILL.md"
    write_skill_md(out, fm, body)
    assert out.exists()
    raw = out.read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    assert "\n---\n" in raw
    parsed_fm = yaml.safe_load(raw.split("---", 2)[1])
    assert parsed_fm["name"] == "ana"
    assert raw.endswith("system prompt\nline 2\n")


def test_write_is_atomic_on_replace_failure(tmp_path: Path, monkeypatch) -> None:
    """os.replace failure → original preserved + no .tmp leftovers."""
    out = tmp_path / "SKILL.md"
    out.write_text("ORIGINAL", encoding="utf-8")
    fm = {"name": "ana", "role": "test", "goal": "x",
          "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.4},
          "tools": []}

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    try:
        write_skill_md(out, fm, "new body")
    except OSError:
        pass

    assert out.read_text(encoding="utf-8") == "ORIGINAL"
    leftovers = list(tmp_path.glob("SKILL.md*.tmp*")) + list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"tmp files leaked: {leftovers}"


def test_write_cleans_tmp_on_write_failure(tmp_path: Path, monkeypatch) -> None:
    """If write/fsync raises mid-flight, no tmp file is left behind."""
    out = tmp_path / "SKILL.md"
    fm = {"name": "ana", "role": "test", "goal": "x",
          "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.4},
          "tools": []}

    real_fsync = __import__("os").fsync

    def boom(_fd):
        raise OSError("disk full")

    monkeypatch.setattr("os.fsync", boom)
    try:
        write_skill_md(out, fm, "body")
    except OSError:
        pass
    finally:
        monkeypatch.setattr("os.fsync", real_fsync)

    assert not out.exists()
    leftovers = list(tmp_path.glob("SKILL.md*.tmp*")) + list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"tmp files leaked: {leftovers}"
