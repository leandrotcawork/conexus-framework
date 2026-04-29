"""CLI entry point for Conexus.

Usage:
    conexus run agent <name>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from conexus.core.agent_handler import handle_agent_message


def _build_execute_tool(registry, agent_name: str):
    async def execute_tool(tool_name: str, args: dict) -> str:
        return await registry.execute_tool(agent_name, tool_name, args)
    return execute_tool


def _make_tools(agent_name: str, agents_dir: Path, data_dir: Path):
    """Dynamically load tools from CONEXUS_AGENTS_DIR/<name>/tools.py.

    Each agent's tools.py must export create_cli_tools(data_dir) -> (store, tools).
    """
    import importlib.util

    tools_path = agents_dir / agent_name / "tools.py"
    if not tools_path.exists():
        raise SystemExit(f"tools.py not found: {tools_path}")

    spec = importlib.util.spec_from_file_location(f"_conexus_agent_{agent_name}_tools", tools_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load tools module from {tools_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    if not hasattr(mod, "create_cli_tools"):
        raise SystemExit(
            f"tools.py for agent '{agent_name}' must export create_cli_tools(data_dir) -> (store, tools). "
            f"See agents/ana/tools.py for an example."
        )

    return mod.create_cli_tools(data_dir)


async def _run_loop(agent_name: str, agents_dir: Path, data_dir: Path) -> None:
    from conexus.core.agent_registry import AgentRegistry
    from conexus.core.budget.cap_checker import CapChecker
    from conexus.core.config.skill_loader import parse_skill_file
    from conexus.core.llm.usage_tracker import UsageTracker
    from conexus.cli.runner import build_runtime

    skill_path = agents_dir / agent_name / "SKILL.md"
    if not skill_path.exists():
        raise SystemExit(f"SKILL.md not found: {skill_path}")

    data_dir.mkdir(parents=True, exist_ok=True)
    store, tools = _make_tools(agent_name, agents_dir, data_dir)

    registry = AgentRegistry()
    registry.register(agent_name, tools)

    tracker = UsageTracker(store)
    execute_tool = _build_execute_tool(registry, agent_name)

    skill = parse_skill_file(skill_path)
    runtime = build_runtime(
        str(skill_path),
        tools_obj=tools,
        execute_tool=execute_tool,
        tracker=tracker,
        agent_name=agent_name,
        system_prompt=skill.body,
    )

    cap_checker = CapChecker(tracker)

    print(f"[conexus] {agent_name} ready. Type your message (Ctrl+C or empty line to quit).")
    while True:
        try:
            line = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not line:
            break

        reply = await handle_agent_message(runtime.handler_cfg, store, cap_checker, line)
        print(f"{agent_name}: {reply}")


def _handle_run_agent(args: argparse.Namespace) -> None:
    agents_dir = Path(os.environ.get("CONEXUS_AGENTS_DIR", "./agents"))
    data_dir = Path(os.environ.get("CONEXUS_DATA_DIR", "./data"))
    asyncio.run(_run_loop(args.name, agents_dir, data_dir))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="conexus",
        description="Conexus agent framework CLI",
    )
    sub = parser.add_subparsers(dest="command")

    run_cmd = sub.add_parser("run", help="Run a sub-command")
    run_sub = run_cmd.add_subparsers(dest="subcommand")

    agent_cmd = run_sub.add_parser("agent", help="Start an agent stdin loop")
    agent_cmd.add_argument("name", help="Agent name (e.g. ana, pesquisador)")
    agent_cmd.set_defaults(func=_handle_run_agent)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
