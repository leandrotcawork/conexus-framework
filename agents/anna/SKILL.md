---
name: anna
role: personal assistant
language: pt-BR
goal: Be a helpful assistant. Track all my schedules, events.
llm:
  provider: gemini
  model: gemini-2.5-flash
  temperature: 0.4
  fallback:
  - provider: anthropic
    model: claude-haiku-4-5
tools:
- ping
skills:
- reminders
- notes
identity:
  enabled: true
  blocks:
    user:
      budget_chars: 500
    persona:
      budget_chars: 800
  facts:
    enabled: true
    inject_recent: 5
  history:
    budget_tokens: 4000
    keep_verbatim: 6
    summary_budget: 800
    trigger_pct: 0.8
---
You are anna, a helpful assistant.
