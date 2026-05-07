---
name: reminders
version: 0.1.0
backend: python
capabilities: [reminders.set, reminders.list, reminders.cancel]
data_classes: {}
budget_hint_usd: 0
---

You can set, list and cancel reminders for the user. Cron syntax is standard 5-field
(`m h dom mon dow`). Use `set_reminder` when the user explicitly asks for a recurring
or scheduled message. Confirm cron back to the user in plain language. Always reply in
the same language the user used.
