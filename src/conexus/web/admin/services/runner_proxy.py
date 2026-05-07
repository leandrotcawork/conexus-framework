"""Wrap build_runtime + handle_agent_message for one-shot REPL invocations.

Sessions are kept in-memory keyed by (agent_name, session_id). The session
holds the registry, tracker, runtime, and store so identity/history persist
across turns within the same browser session.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conexus.cli.runner import build_runtime
from conexus.core.agent_handler import handle_agent_message
from conexus.core.agent_registry import AgentRegistry
from conexus.core.budget.cap_checker import CapChecker
from conexus.core.config.skill_loader import parse_skill_file
from conexus.core.llm.usage_tracker import UsageTracker


@dataclass
class _Session:
    registry: Any
    tracker: Any
    runtime: Any
    store: Any
    cap_checker: Any


_SESSIONS: dict[tuple[str, str], _Session] = {}


def _build_session(agent_name: str, agents_dir: Path, data_dir: Path) -> _Session:
    tools_path = agents_dir / agent_name / "tools.py"
    skill_path = agents_dir / agent_name / "SKILL.md"

    spec = importlib.util.spec_from_file_location(f"_studio_tools_{agent_name}", tools_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import tools.py for {agent_name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    store, tools = mod.create_cli_tools(data_dir)

    registry = AgentRegistry()
    registry.register(agent_name, tools)
    tracker = UsageTracker(store)

    async def execute_tool(tool_name: str, args: dict) -> str:
        return await registry.execute_tool(agent_name, tool_name, args)

    skill = parse_skill_file(skill_path)
    runtime = build_runtime(
        str(skill_path),
        tools_obj=tools,
        execute_tool=execute_tool,
        tracker=tracker,
        agent_name=agent_name,
        system_prompt=skill.body,
        store=store,
    )
    return _Session(
        registry=registry,
        tracker=tracker,
        runtime=runtime,
        store=store,
        cap_checker=CapChecker(tracker),
    )


async def run_one_message(
    agent_name: str, message: str, *, agents_dir: Path, data_dir: Path, session_id: str
) -> str:
    key = (agent_name, session_id)
    if key not in _SESSIONS:
        _SESSIONS[key] = _build_session(agent_name, agents_dir, data_dir)
    s = _SESSIONS[key]
    return await handle_agent_message(s.runtime.handler_cfg, s.store, s.cap_checker, message)


def reset_session(agent_name: str, session_id: str) -> None:
    _SESSIONS.pop((agent_name, session_id), None)
