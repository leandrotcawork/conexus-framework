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
