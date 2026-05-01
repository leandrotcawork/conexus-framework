import pytest
from conexus.core.team.team_pack import parse_team_pack, TeamPackDocument
from conexus.core.team.team_loader import TeamLoader

PACK_MD = """---
name: product_team
version: 0.1.0
manager: pm
members: [ana, pm, researcher]
edges:
  - {from: pm, to: researcher, when: "task.kind == 'research'"}
  - {from: researcher, to: pm, auto: true}
budget:
  team_daily_usd: 1.00
  shares: {ana: 0.2, pm: 0.4, researcher: 0.4}
  on_share_exceeded: notify
policy:
  trifecta_enforcement: strict
  max_hops: 5
  max_turns: 20
  termination_text: DONE
---
Team body fragment.
"""


def test_parse_team_pack(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    doc = parse_team_pack(tmp_path / "TEAM_PACK.md")
    assert doc.frontmatter.name == "product_team"
    assert doc.frontmatter.manager == "pm"
    assert doc.frontmatter.members == ["ana", "pm", "researcher"]
    assert doc.frontmatter.edges[0]["from"] == "pm"
    assert doc.frontmatter.budget.team_daily_usd == 1.00
    assert doc.frontmatter.policy.max_hops == 5


def test_parse_missing_frontmatter_fails(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text("no frontmatter")
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        parse_team_pack(tmp_path / "TEAM_PACK.md")


def test_team_loader_validates_member_exists(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD.replace("[ana, pm, researcher]", "[ana, pm, ghost]"))
    available = {"ana", "pm", "researcher"}
    loader = TeamLoader(available_agents=available)
    with pytest.raises(ValueError, match="unknown member: ghost"):
        loader.load(tmp_path / "TEAM_PACK.md")


def test_team_loader_returns_document(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    loader = TeamLoader(available_agents={"ana", "pm", "researcher"})
    doc = loader.load(tmp_path / "TEAM_PACK.md")
    assert isinstance(doc, TeamPackDocument)
