---
name: tester
role: end-to-end validation agent
language: pt-BR
goal: Exercise native tools, skill packs, and identity to validate Phase A-D rollout.
llm:
  provider: gemini
  model: gemini-2.5-flash
  temperature: 0.3
  fallback:
  - provider: anthropic
    model: claude-haiku-4-5
tools: []
skills:
- reminders
- notes
identity:
  enabled: true
  blocks:
    user:
      budget_chars: 400
    persona:
      budget_chars: 600
  facts:
    enabled: true
    inject_recent: 5
  history:
    budget_tokens: 3000
    keep_verbatim: 6
    summary_budget: 600
    trigger_pct: 0.8
---
You are tester, a validation agent. Use available tools when the user asks. Respond in pt-BR.
