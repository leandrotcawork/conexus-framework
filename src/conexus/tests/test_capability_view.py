# src/conexus/tests/test_capability_view.py
from pathlib import Path
import pytest
from conexus.web.admin.services.capability_view import build_capability_view


def test_aggregator_returns_four_sections(tmp_path: Path):
    agent_dir = tmp_path / "agents" / "ana"
    agent_dir.mkdir(parents=True)
    (agent_dir / "tools.py").write_text(
        "class T:\n    def ping(self) -> str: ...\n"
    )
    view = build_capability_view(
        agent_dir=agent_dir,
        skill_refs=[],
        identity_enabled=True,
        connector_registry=tmp_path / "missing.json",
        packs_root=tmp_path / "packs",
        model="gpt-4o-mini",
    )
    assert "native" in view
    assert "identity" in view
    assert "packs" in view
    assert "connectors" in view
    assert len(view["native"]) == 1
    assert view["native"][0].name == "ping"
    assert view["connectors"] == []


from fastapi.testclient import TestClient


def test_detail_view_renders_capability(studio_client: TestClient):
    r = studio_client.get("/admin/agents/ana")
    assert r.status_code == 200
    assert "Skill Packs" in r.text
    assert "Connectors" in r.text
