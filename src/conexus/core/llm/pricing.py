"""LLM utilities — provider list and cost calculation via LiteLLM."""

from __future__ import annotations

# Providers we support (we own API key management for these).
# Model names within each provider are derived from LiteLLM's catalog.
SUPPORTED_PROVIDERS: list[str] = [
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "groq",
]

# Keywords that indicate non-chat-completion specialized models.
_EXCLUDE: tuple[str, ...] = (
    "audio", "realtime", "tts", "search", "native", "live",
    "robotics", "container", "lyria", "learnlm", "image",
    "embedding", "ft:", "video", "vision", "ocr",
    "computer-use", "customtools",
)

USD_TO_BRL: float = 5.00  # Update periodically.


def llm_options() -> dict[str, list[str]]:
    """Return {provider: [model, ...]} from LiteLLM's catalog.

    Provider list is ours to maintain (API keys).
    Model names are LiteLLM's responsibility — auto-updated when they release new ones.
    """
    import litellm

    result: dict[str, list[str]] = {}
    seen: set[str] = set()

    for key, info in litellm.model_cost.items():
        if info.get("mode") != "chat":
            continue

        # Resolve provider + model name
        if "/" in key:
            provider, model = key.split("/", 1)
            if "/" in model:  # skip nested paths like meta-llama/llama-x
                continue
        else:
            provider = info.get("litellm_provider", "")
            model = key

        if provider not in SUPPORTED_PROVIDERS:
            continue

        # Skip specialized / non-text-chat models
        lower = model.lower()
        if any(ex in lower for ex in _EXCLUDE):
            continue

        dedup_key = f"{provider}/{model}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        result.setdefault(provider, []).append(model)

    # Preserve provider order
    return {p: sorted(result[p]) for p in SUPPORTED_PROVIDERS if p in result}


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return cost in USD for a call given token counts.

    Delegates to litellm.cost_per_token — always uses their up-to-date table.
    Returns 0.0 on any error (unknown model, missing pricing).
    """
    try:
        import litellm
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        return prompt_cost + completion_cost
    except Exception:
        return 0.0
