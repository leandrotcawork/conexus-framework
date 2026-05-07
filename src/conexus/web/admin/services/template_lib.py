"""Agent scaffolding templates."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .skill_writer import write_skill_md

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")

_TOOLS_PY = '''"""Tools for {name}."""
from __future__ import annotations

from typing import ClassVar

from conexus.core.memory.sqlite_store import SqliteStore


class {cls}:
    """Public methods are callable by the agent. Underscore methods are hidden."""

    _tool_schemas: ClassVar[dict] = {{
        "ping": {{"description": "Health check.", "params": {{}}}},
    }}

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def ping(self) -> dict:
        """Health check."""
        return {{"ok": True}}


def create_cli_tools(data_dir):
    store = SqliteStore(str(data_dir) + "/conexus.db")
    return store, {cls}(store)
'''


def _tools_class_name(agent: str) -> str:
    return "".join(p.capitalize() for p in agent.split("_")) + "Tools"


def _base_frontmatter(name: str) -> dict:
    return {
        "name": name,
        "role": "personal assistant",
        "language": "pt-BR",
        "goal": "Be a helpful assistant.",
        "llm": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.4,
            "fallback": [{"provider": "anthropic", "model": "claude-haiku-4-5"}],
        },
        "tools": ["ping"],
    }


def _identity_block() -> dict:
    return {
        "enabled": True,
        "blocks": {"user": {"budget_chars": 500}, "persona": {"budget_chars": 800}},
        "facts": {"enabled": True, "inject_recent": 5},
        "history": {
            "budget_tokens": 4000,
            "keep_verbatim": 6,
            "summary_budget": 800,
            "trigger_pct": 0.80,
        },
    }


TEMPLATES = ("chat-only", "chat+memory", "chat+memory+gcal")


def scaffold_agent(agents_dir: Path, name: str, *, template: str) -> Path:
    if template not in TEMPLATES:
        raise ValueError(f"unknown template: {template}")
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid agent name: {name!r} (must match {_NAME_RE.pattern})")

    d = agents_dir / name
    if d.exists():
        raise FileExistsError(f"agent exists: {d}")
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    (d / "tools.py").write_text(_TOOLS_PY.format(name=name, cls=_tools_class_name(name)))

    fm = _base_frontmatter(name)
    if template in ("chat+memory", "chat+memory+gcal"):
        fm["identity"] = _identity_block()
    if template == "chat+memory+gcal":
        fm["skills"] = ["google_calendar@1.0"]
        pack = d / "skills" / "google_calendar"
        pack.mkdir(parents=True)
        (pack / "SKILL_PACK.md").write_text(
            "---\nname: google_calendar\nversion: \"1.0\"\nbackend: mcp-http\n"
            "capabilities: []\ndata_classes: {}\n---\nGoogle Calendar.\n"
        )
        (pack / "connector.json").write_text(json.dumps({
            "server_url": "https://mcp.google.com/calendar",
            "scopes": [
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/calendar.events",
            ],
            "ui": {
                "label": "Google Calendar",
                "icon": "🗓",
                "category": "Productivity",
                "description": "Read and create events.",
            },
        }, indent=2))

    write_skill_md(d / "SKILL.md", fm, f"You are {name}, a helpful assistant.\n")
    return d
