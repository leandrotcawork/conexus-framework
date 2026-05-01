"""Pip-install smoke test + deployment field round-trip (Codex B-7 + B-8)."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
import pytest


@pytest.mark.slow
def test_pip_install_wheel_works(tmp_path):
    """Build wheel + install in a fresh venv + import conexus.cli.__main__."""
    repo_root = Path(__file__).resolve().parents[3]
    wheel_dir = tmp_path / "dist"
    wheel_dir.mkdir()
    subprocess.check_call(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(wheel_dir)],
        cwd=str(repo_root),
    )
    wheels = list(wheel_dir.glob("conexus-*.whl"))
    assert wheels, "no wheel produced"
    venv_dir = tmp_path / "venv"
    subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
    pip = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    py = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    subprocess.check_call([str(pip), "install", str(wheels[0])])
    subprocess.check_call([str(py), "-c", "from conexus.cli import __main__"])


def test_deployment_field_round_trips(tmp_path):
    """deployment: in TEAM_PACK frontmatter survives parse → registry."""
    from conexus.core.team.team_loader import TeamLoader
    p = tmp_path / "TEAM_PACK.md"
    p.write_text(
        "---\n"
        "name: t\nversion: '1'\nmanager: ana\nmembers: [ana, pm]\nedges: []\n"
        "budget: {team_daily_usd: 1.0, shares: {ana: 0.5, pm: 0.5}}\n"
        "deployment:\n"
        "  region: gru\n"
        "  process: telegram\n"
        "---\n"
    )
    doc = TeamLoader({"ana", "pm"}).load(str(p))
    assert doc.frontmatter.deployment == {"region": "gru", "process": "telegram"}
