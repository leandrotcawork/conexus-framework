"""Wrap build_runtime + handle_agent_message for one-shot REPL invocations.

Sessions are kept in-memory keyed by (agent_name, session_id). The session
holds the registry, tracker, runtime, store, and any loaded skill-pack
backends so identity/history/packs persist across turns within the same
browser session.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conexus.cli.runner import build_runtime
from conexus.core.agent_handler import handle_agent_message
from conexus.core.agent_registry import AgentRegistry
from conexus.core.backends.python_backend import PythonBackend
from conexus.core.budget.cap_checker import CapChecker
from conexus.core.config.skill_loader import parse_skill_file
from conexus.core.llm.usage_tracker import UsageTracker
from conexus.core.skills.skill_resolver import SkillLoader
from conexus.core.tools.schema_gen import generate_tool_schemas


@dataclass
class _Session:
    registry: Any
    tracker: Any
    runtime: Any
    store: Any
    cap_checker: Any
    loader: SkillLoader | None = None


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

    # Load skill packs declared in SKILL.md and merge their prompt fragments.
    # Packs live under <repo>/packs/<id>/; pack_ctx provides the shared store
    # and agent_name so per-agent rows (e.g. pack_notes_entries.agent_name) are
    # scoped correctly.
    packs_root = agents_dir.parent / "packs"
    loader = SkillLoader(
        agent_dir=agents_dir / agent_name,
        registry=registry,
        agent_name=agent_name,
        packs_root=packs_root,
        pack_ctx={"store": store, "agent_name": agent_name},
    )
    pack_prompt, _tags = loader.load(skill.frontmatter.skills)
    system_prompt = skill.body + (("\n\n" + pack_prompt) if pack_prompt else "")

    runtime = build_runtime(
        str(skill_path),
        tools_obj=tools,
        execute_tool=execute_tool,
        tracker=tracker,
        agent_name=agent_name,
        system_prompt=system_prompt,
        store=store,
    )

    # Mirror CLI _run_loop: register identity tools as a second backend so the
    # 12 identity verbs (remember_*, get_*, ...) become callable.
    if runtime.identity is not None:
        registry.register_backend(agent_name, PythonBackend(runtime.identity.tools))

    # Extend handler tools_schema with pack + identity tool schemas. build_runtime()
    # only generates schemas for the native tools class (skill.frontmatter.tools);
    # without this merge the LLM cannot see pack/identity tools even though
    # AgentRegistry routes their calls correctly.
    existing = {s["function"]["name"] for s in runtime.handler_cfg.tools_schema}
    backends = registry._backends.get(agent_name, [])
    for backend in backends[1:]:  # skip native (index 0)
        if not isinstance(backend, PythonBackend):
            continue
        names = [n for n in backend.list_tools() if n not in existing]
        if not names:
            continue
        for schema in generate_tool_schemas(type(backend._tools), names):
            runtime.handler_cfg.tools_schema.append(schema)
            existing.add(schema["function"]["name"])

    return _Session(
        registry=registry,
        tracker=tracker,
        runtime=runtime,
        store=store,
        cap_checker=CapChecker(tracker),
        loader=loader,
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


def _clear_all_sessions() -> None:
    """Test helper — clears all in-memory sessions."""
    _SESSIONS.clear()
