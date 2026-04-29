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


def _make_tools(agent_name: str, data_dir: Path):
    from conexus.core.memory.sqlite_store import SqliteStore
    from conexus.core.memory.wiki_store import WikiStore

    store = SqliteStore(data_dir / "conexus.db")

    if agent_name == "ana":
        from agents.ana.tools import AnaTools
        wiki = WikiStore(data_dir / "wiki", autocommit=False)
        tools = AnaTools(store=store, wiki=wiki, calendar=None)
        return store, tools

    if agent_name == "pesquisador":
        from agents.pesquisador.tools import PesquisadorTools
        wiki = WikiStore(data_dir / "knowledge", autocommit=False)
        tools = PesquisadorTools(wiki=wiki, llm_synthesis=None)
        return store, tools

    raise SystemExit(f"Unknown agent '{agent_name}'. Supported: ana, pesquisador")


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
    store, tools = _make_tools(agent_name, data_dir)

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
