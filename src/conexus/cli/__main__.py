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


def _handle_tag_suggest(args: argparse.Namespace) -> None:
    """Print auto-tag suggestions for every public method in a tools.py."""
    import importlib.util as _ilu
    from conexus.core.trifecta.tags import auto_tag

    path = Path(args.tools_file)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    spec = _ilu.spec_from_file_location("_tag_target", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {path}")
    import sys as _sys
    mod = _ilu.module_from_spec(spec)
    _sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        del _sys.modules[spec.name]
        raise SystemExit(f"Error loading {path}: {exc}") from exc

    classes = [(n, v) for n, v in vars(mod).items() if isinstance(v, type) and not n.startswith("_")]
    if not classes:
        print("# No classes found.")
        return

    print("# Suggested data_classes: (review before committing)")
    print("data_classes:")
    untagged: list[str] = []
    for cls_name, cls in classes:
        methods = [m for m in dir(cls) if not m.startswith("_") and callable(getattr(cls, m))]
        for method in methods:
            tag = auto_tag(method)
            if tag:
                print(f"  {method}: {tag.value}")
            else:
                untagged.append(method)

    if untagged:
        print("# --- Untagged (manual review required) ---")
        for m in untagged:
            print(f"  {m}: ???  # add to SKILL_PACK.md data_classes")


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

    tag_cmd = sub.add_parser("tag", help="Tag analysis utilities")
    tag_sub = tag_cmd.add_subparsers(dest="subcommand")
    suggest_cmd = tag_sub.add_parser("suggest", help="Print suggested data_classes for a tools.py")
    suggest_cmd.add_argument("tools_file", help="Path to a tools.py file")
    suggest_cmd.set_defaults(func=_handle_tag_suggest)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
