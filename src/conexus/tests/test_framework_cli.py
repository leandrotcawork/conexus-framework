def test_cli_run_team_validates_pack(tmp_path, capsys, monkeypatch):
    # Pack with unknown member should error and exit nonzero.
    pack = tmp_path / "TEAM_PACK.md"
    pack.write_text(
        "---\nname: t\nversion: 0.1.0\nmanager: pm\nmembers: [ghost]\n"
        "budget: {team_daily_usd: 1.0, shares: {ghost: 1.0}}\n---\n"
    )
    from conexus.cli.__main__ import _handle_run_team
    import argparse
    args = argparse.Namespace(pack=str(pack), available_agents="ana,pm,researcher")
    rc = _handle_run_team(args)
    assert rc != 0
    assert "unknown member" in capsys.readouterr().out.lower()


def test_studio_and_legacy_subcommands_parse() -> None:
    from conexus.cli.__main__ import _build_parser

    parser = _build_parser()

    studio = parser.parse_args(["studio", "--port", "8765"])
    assert studio.command == "studio" and studio.port == 8765 and callable(studio.func)

    run_agent = parser.parse_args(["run", "agent", "ana"])
    assert run_agent.command == "run" and run_agent.name == "ana" and callable(run_agent.func)

    tag = parser.parse_args(["tag", "suggest", "agents/ana/tools.py"])
    assert tag.command == "tag" and tag.tools_file.endswith("tools.py")

    inst = parser.parse_args(["connectors", "install", "google_calendar", "--agent", "ana"])
    assert inst.command == "connectors" and inst.action == "install" and inst.agent == "ana"
