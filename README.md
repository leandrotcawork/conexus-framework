# Conexus

Personal AI agent framework. First agent: **Ana**, a Brazilian-Portuguese
secretary.

See `docs/specs/2026-04-11-conexus-secretary-design.md` for the full design.
See `docs/plans/2026-04-12-conexus-secretary-implementation.md` for the
implementation plan.

## Quick start

```bash
uv sync
uv run pytest
uv run python main.py
```

## Environment

Copy `.env.example` to `.env` and fill in the values. See the design doc
for secret provenance.
