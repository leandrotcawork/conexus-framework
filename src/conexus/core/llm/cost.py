"""LLM call cost — prefer litellm pre-computed, fall back to cost_per_token."""
from __future__ import annotations
from typing import Any


def cost_from_response(resp: Any) -> float:
    hp = getattr(resp, "_hidden_params", {}) or {}
    pre = hp.get("response_cost")
    if pre is not None:
        return float(pre)
    import litellm
    try:
        usage = getattr(resp, "usage", None)
        if usage is None:
            return 0.0
        prompt, completion = litellm.cost_per_token(
            model=getattr(resp, "model", ""),
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
        return prompt + completion
    except Exception:
        return 0.0
