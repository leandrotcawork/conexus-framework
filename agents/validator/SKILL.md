---
name: validator
role: e2e validation agent
language: pt-BR
goal: Exercise tools, skill packs, and identity to validate the full framework stack.
llm:
  provider: deepseek
  model: deepseek-v4-flash
  temperature: 0.3
  fallback:
  - provider: gemini
    model: gemini-2.5-flash
tools:
- ping
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
  wiki:
    backend: local
    dir: ./wiki
    inject_index: true
  history:
    budget_tokens: 3000
    keep_verbatim: 6
    summary_budget: 600
    trigger_pct: 0.8
---
You are validator, a framework validation agent. When asked to test something, use the available tools and packs explicitly — don't simulate. Respond in pt-BR.
