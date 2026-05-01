---
name: product_team
version: 0.1.0
manager: pm
members:
  - ana
  - pm
  - researcher

edges:
  - {from: ana, to: pm, when: "task.kind == 'plan'"}
  - {from: pm, to: researcher, when: "task.kind == 'research'"}
  - {from: researcher, to: pm, auto: true}

budget:
  team_daily_usd: 1.00
  shares:
    ana: 0.20
    pm: 0.40
    researcher: 0.40
  on_share_exceeded: notify

policy:
  trifecta_enforcement: strict
  max_hops: 5
  max_turns: 20
  termination_text: "DONE"

deployment:
  ana: cloud
  pm: cloud
  researcher: cloud
---
# Product team — body fragment

Three-member team. Ana fronts user requests; pm orchestrates plan + research;
researcher does external reads (web_fetch, web_search).

Default flow: user → ana → pm → researcher → pm → wiki_write.
