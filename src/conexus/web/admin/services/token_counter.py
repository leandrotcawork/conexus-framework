"""Estimate tokens consumed by tool schemas in a system prompt."""
from __future__ import annotations

import json


def count_schema_tokens(schemas: list[dict], *, model: str) -> int:
    if not schemas:
        return 0
    try:
        import litellm
        text = json.dumps(schemas, ensure_ascii=False)
        return int(litellm.token_counter(model=model, text=text))
    except Exception:
        return 0
