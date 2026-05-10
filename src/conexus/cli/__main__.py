"""CLI entry point for Conexus.

Usage:
    conexus run agent <name>
"""

from __future__ import annotations

import argparse
import asyncio
import os
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
    from conexus.core.llm import telemetry
    from conexus.core.llm.usage_tracker import UsageTracker
    from conexus.cli.runner import build_runtime

    skill_path = agents_dir / agent_name / "SKILL.md"
    if not skill_path.exists():
        raise SystemExit(f"SKILL.md not found: {skill_path}")

    data_dir.mkdir(parents=True, exist_ok=True)
    store, tools = _make_tools(agent_name, agents_dir, data_dir)
    telemetry.install(store)

    registry = AgentRegistry()
    registry.register(agent_name, tools)

    tracker = UsageTracker(store)
    execute_tool = _build_execute_tool(registry, agent_name)

    skill = parse_skill_file(skill_path)
    runtime = build_runtime(
        str(skill_path),
        tools_obj=tools,
        execute_tool=execute_tool,
        agent_name=agent_name,
        system_prompt=skill.body,
        store=store,
    )

    # Register identity tools as a second backend when identity is active
    if runtime.identity is not None:
        from conexus.core.backends.python_backend import PythonBackend
        registry.register_backend(agent_name, PythonBackend(runtime.identity.tools))

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


def _handle_mcp_server(args: argparse.Namespace) -> None:
    import os
    from conexus.core.mcp.producer import build_mcp_producer
    token = os.environ.get("CONEXUS_MCP_TOKEN", "")
    if not token:
        raise SystemExit("CONEXUS_MCP_TOKEN env var required")
    server = build_mcp_producer(wiki_root=args.wiki_root, bearer_token=token)
    server.run(transport="stdio")


def _handle_replay(args: argparse.Namespace) -> None:
    import sqlite3
    from conexus.core.memory.handoff_audit import init_handoff_audit
    from conexus.core.memory.tool_audit import init_tool_audit
    from conexus.core.team.replay import replay_session
    from conexus.core.team.team_loader import TeamLoader
    from conexus.core.team.team_registry import TeamRegistry

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    available = set(filter(None, args.available_agents.split(","))) if args.available_agents else None
    doc = TeamLoader(available or set()).load(args.pack)
    registry = TeamRegistry(doc)

    conn = sqlite3.connect(db_path)
    try:
        init_handoff_audit(conn)
        init_tool_audit(conn)
        report = replay_session(conn, session_id=args.session_id, registry=registry)
    finally:
        conn.close()

    print(f"handoffs_replayed: {report.handoffs_replayed}")
    print(f"tools_replayed:    {report.tools_replayed}")
    if report.mismatches:
        print(f"mismatches ({len(report.mismatches)}):")
        for m in report.mismatches:
            print(f"  [{m.kind}] expected={m.expected!r} actual={m.actual!r} {m.detail}")
    else:
        print("mismatches: none")


def _handle_run_team(args) -> int:
    from conexus.core.team.team_loader import TeamLoader
    available = set(filter(None, args.available_agents.split(",")))
    try:
        doc = TeamLoader(available).load(args.pack)
    except Exception as exc:
        print(f"team load failed: {exc}")
        return 1
    print(f"loaded team {doc.frontmatter.name}: {doc.frontmatter.members}")
    return 0


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


def _cmd_connectors(args: argparse.Namespace) -> None:
    import json as _json
    from conexus.core.connectors.registry import ConnectorRegistry

    registry_path = getattr(args, "registry", None) or "connectors/registry.json"
    reg = ConnectorRegistry.from_file(registry_path)

    if args.action == "list":
        for e in reg.list():
            print(f"{e.name:24} {e.version:8} {e.ui_category:14} {e.ui_label}")
            print(f"  {e.ui_description}")

    elif args.action == "install":
        e = reg.get(args.name)
        if not e:
            raise SystemExit(f"unknown connector: {args.name}")
        target = Path("agents") / args.agent / "skills" / e.name
        target.mkdir(parents=True, exist_ok=True)
        (target / "SKILL_PACK.md").write_text(
            f"---\n"
            f"name: {e.name}\n"
            f'version: "{e.version}"\n'
            f"backend: mcp-http\n"
            f"capabilities: []\n"
            f"data_classes: {{}}\n"
            f"---\n"
            f"{e.ui_description}\n",
            encoding="utf-8",
        )
        (target / "connector.json").write_text(_json.dumps({
            "server_url": e.server_url,
            "scopes": e.scopes,
            "ui": {
                "label": e.ui_label, "icon": e.ui_icon,
                "category": e.ui_category, "description": e.ui_description,
            },
        }, indent=2))
        print(f"installed {e.name} → {target}")
        print(f"add '{e.name}@{e.version}' to agents/{args.agent}/SKILL.md skills:")

    elif args.action == "connect":
        import secrets as _secrets
        from conexus.core.oauth.state import encode_state

        e = reg.get(args.name)
        if not e:
            raise SystemExit(f"unknown connector: {args.name}")
        secret_str = os.environ.get("CONEXUS_STATE_SECRET", "")
        if not secret_str:
            raise SystemExit("CONEXUS_STATE_SECRET env var required")
        secret = secret_str.encode()
        nonce = _secrets.token_urlsafe(16)
        state = encode_state(
            secret, user_id=args.user, server_url=e.server_url,
            return_to=getattr(args, "return_to", None) or "",
            nonce=nonce,
        )
        base = os.environ.get("CONEXUS_OAUTH_BASE", "http://localhost:8000")
        print(f"{base}/oauth/start?state={state}")


def _handle_studio(args: argparse.Namespace) -> None:
    import webbrowser

    import uvicorn

    from conexus.web.admin.app import make_admin_app

    # Load .env from CWD so LLM keys (GEMINI/ANTHROPIC/OPENAI) reach the runtime
    # without requiring the launcher to export them. No-op if dotenv missing or
    # .env absent.
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]
        load_dotenv()
    except ImportError:
        pass

    agents_dir = Path(os.environ.get("CONEXUS_AGENTS_DIR", "./agents"))
    data_dir = Path(os.environ.get("CONEXUS_DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    app = make_admin_app(agents_dir=agents_dir, data_dir=data_dir)
    url = f"http://127.0.0.1:{args.port}/admin/"
    print(f"[conexus] Studio running at {url}")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


def _handle_wiki_migrate(args: argparse.Namespace) -> None:
    from conexus.cli.wiki_migrate import migrate_agent_wiki
    from conexus.core.memory.sqlite_store import SqliteStore
    from conexus.core.memory.wiki.local import LocalBackend

    store = SqliteStore(f"{args.data_dir}/conexus.db")
    store.init_db()
    backend = LocalBackend(Path(args.agents_dir) / args.agent / "wiki")
    res = migrate_agent_wiki(args.agent, backend, store)
    print(res)


def _build_parser() -> argparse.ArgumentParser:
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

    mcp_p = sub.add_parser("mcp-server", help="Run Conexus as an MCP server (stdio)")
    mcp_p.add_argument("--wiki-root", default="./data/wiki")
    mcp_p.set_defaults(func=_handle_mcp_server)

    replay_p = sub.add_parser("replay", help="Replay a frozen audit session against a registry")
    replay_p.add_argument("pack", help="Path to TEAM_PACK.md")
    replay_p.add_argument("--db", required=True, help="Path to SQLite DB")
    replay_p.add_argument("--session-id", required=True, help="Session ID to replay")
    replay_p.add_argument("--available-agents", default="", help="Comma-sep agent names")
    replay_p.set_defaults(func=_handle_replay)

    team_p = sub.add_parser(
        "run-team",
        help="Validate + load a TEAM_PACK (Phase 8: validate-only; runtime in Phase 9)",
    )
    team_p.add_argument("pack", help="path to TEAM_PACK.md")
    team_p.add_argument("--available-agents", default="", help="comma-sep agent names available")
    team_p.set_defaults(func=_handle_run_team)

    connectors_p = sub.add_parser("connectors", help="Manage MCP connectors")
    connectors_sub = connectors_p.add_subparsers(dest="action")

    conn_list = connectors_sub.add_parser("list", help="List available connectors")
    conn_list.add_argument("--registry", default=None, help="Path to registry.json")
    conn_list.set_defaults(func=_cmd_connectors, action="list")

    conn_install = connectors_sub.add_parser("install", help="Install a connector pack")
    conn_install.add_argument("name", help="Connector name")
    conn_install.add_argument("--agent", required=True, help="Agent directory name")
    conn_install.add_argument("--registry", default=None)
    conn_install.set_defaults(func=_cmd_connectors, action="install")

    conn_connect = connectors_sub.add_parser("connect", help="Generate OAuth start link")
    conn_connect.add_argument("name", help="Connector name")
    conn_connect.add_argument("--user", required=True, help="User ID")
    conn_connect.add_argument("--return-to", dest="return_to", default=None)
    conn_connect.add_argument("--registry", default=None)
    conn_connect.set_defaults(func=_cmd_connectors, action="connect")

    studio_p = sub.add_parser("studio", help="Start Conexus Studio web UI on 127.0.0.1")
    studio_p.add_argument("--port", type=int, default=8765)
    studio_p.add_argument("--no-browser", action="store_true")
    studio_p.set_defaults(func=_handle_studio)

    wiki_p = sub.add_parser("wiki", help="wiki maintenance")
    wiki_sub = wiki_p.add_subparsers(dest="wiki_cmd")
    mig = wiki_sub.add_parser("migrate", help="inject frontmatter + build FTS index")
    mig.add_argument("--agent", required=True)
    mig.add_argument("--data-dir", default="./data")
    mig.add_argument("--agents-dir", default="./agents")
    mig.set_defaults(func=_handle_wiki_migrate)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return
    func(args)


if __name__ == "__main__":
    main()
