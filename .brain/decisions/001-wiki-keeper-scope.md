# ADR-001: wiki-keeper scope locked to docs/wiki/agents-framework/

**Date:** 2026-04-29
**Status:** accepted

## Context
wiki-keeper is a Bash-capable subagent that edits wiki files. Without a scope
restriction it could modify any file in the repo, making it dangerous to dispatch
after any trigger.

## Decision
wiki-keeper may only read/write `docs/wiki/agents-framework/*.md`. Hard rule
enforced in the subagent definition. Smoke test confirmed it refuses out-of-scope
requests.

## Rationale
Minimal blast radius. The wiki is the only output that needs maintenance; other
docs (dev-workflow, specs, plans) have clear human ownership. Scope restriction
also makes the subagent's behavior predictable and auditable.

## Consequences
wiki-keeper cannot update `docs/dev-workflow/` or `docs/superpowers/` even if
triggered by changes there. Those updates remain manual or require a different
subagent.

## Alternatives Considered
- Unrestricted scope: rejected — too risky for an always-on subagent
- Per-trigger scope override: rejected — adds complexity, undermines the hard-rule guarantee
