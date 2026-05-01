"""End-to-end: ana delegates to pm; pm delegates to researcher; researcher
web_fetch (untrusted_read) + wiki_search (private_read); back to pm; pm tries
wiki_write — must be blocked by cross-agent TrifectaGuard."""

import pytest
from conexus.core.team.handoff import Handoff
from conexus.core.team.handoff_router import HandoffRouter
from conexus.core.team.team_loader import TeamLoader
from conexus.core.team.team_registry import TeamRegistry
from conexus.core.team.budget_cascader import BudgetCascader, BudgetPolicy
from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation
from conexus.core.trifecta.tags import DataClass

PACK_MD = """---
name: t
version: 0.1.0
manager: pm
members: [ana, pm, researcher]
edges:
  - {from: pm, to: researcher, when: "task.kind == 'research'"}
  - {from: researcher, to: pm, auto: true}
budget:
  team_daily_usd: 1.0
  shares: {ana: 0.2, pm: 0.4, researcher: 0.4}
  on_share_exceeded: notify
policy:
  max_hops: 5
---
"""


def test_full_team_flow_blocks_exfil(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    reg = TeamRegistry(TeamLoader({"ana", "pm", "researcher"}).load(tmp_path / "TEAM_PACK.md"))
    router = HandoffRouter(reg)
    cascader = BudgetCascader(reg.budget.team_daily_usd, reg.budget.shares, BudgetPolicy.notify)

    # ana → pm
    _h1 = Handoff(from_agent="ana", to_agent="pm", payload={"task": {"kind": "plan"}})
    assert cascader.check_and_debit("pm", 0.05) is True

    # pm → researcher (kind=research routes via edge)
    h2 = Handoff(from_agent="pm", to_agent="auto", payload={"task": {"kind": "research"}})
    assert router.route(h2) == "researcher"
    assert cascader.check_and_debit("researcher", 0.05) is True

    # researcher reads web (untrusted) + wiki (private). taint accumulates.
    researcher_guard = TrifectaGuard(
        {"web_fetch": "untrusted_read", "wiki_search": "private_read", "wiki_write": "external_write"}
    )
    researcher_guard.check_and_record("web_fetch")
    researcher_guard.check_and_record("wiki_search")

    # researcher returns Handoff to pm — taint travels.
    h3 = Handoff(
        from_agent="researcher",
        to_agent="pm",
        payload={"summary": "..."},
        tags={DataClass.untrusted_read, DataClass.private_read},
        hop_count=2,
    )

    # pm receives — guard seeded with researcher's taint
    pm_guard = TrifectaGuard.from_handoff({"wiki_write": "external_write"}, h3)
    with pytest.raises(TrifectaViolation):
        pm_guard.check_and_record("wiki_write")  # blocked by cross-agent taint


def test_full_team_flow_allows_with_trust_cleared(tmp_path):
    (tmp_path / "TEAM_PACK.md").write_text(PACK_MD)
    _reg = TeamRegistry(TeamLoader({"ana", "pm", "researcher"}).load(tmp_path / "TEAM_PACK.md"))

    h = Handoff(
        from_agent="researcher",
        to_agent="pm",
        payload={},
        tags={DataClass.untrusted_read, DataClass.private_read},
        trust_boundary_cleared=True,
    )
    pm_guard = TrifectaGuard.from_handoff({"wiki_write": "external_write"}, h)
    pm_guard.check_and_record("wiki_write")  # explicit override allowed
