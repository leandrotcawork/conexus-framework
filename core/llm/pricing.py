"""LLM pricing table. Verify numbers on provider pages before deploy."""

from __future__ import annotations

# USD per 1M tokens. input = prompt tokens; output = completion tokens.
PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "anthropic/claude-haiku-4-5":     {"input": 1.00,  "output": 5.00},
    "anthropic/claude-sonnet-4-5":    {"input": 3.00,  "output": 15.00},
    "anthropic/claude-opus-4-6":      {"input": 15.00, "output": 75.00},
    # OpenAI
    "openai/gpt-4o-mini":             {"input": 0.15,  "output": 0.60},
    "openai/gpt-4o":                  {"input": 2.50,  "output": 10.00},
    # Google
    "gemini/gemini-2.0-flash":        {"input": 0.075, "output": 0.30},
    "gemini/gemini-1.5-pro":          {"input": 1.25,  "output": 5.00},
    # DeepSeek
    "deepseek/deepseek-chat":         {"input": 0.27,  "output": 1.10},
    "deepseek/deepseek-reasoner":     {"input": 0.55,  "output": 2.19},
    # Groq
    "groq/llama-3.3-70b-versatile":   {"input": 0.59,  "output": 0.79},
}

USD_TO_BRL: float = 5.00  # Update periodically.


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return cost in USD for a single LLM call. Returns 0.0 for unknown models."""
    price = PRICING.get(model)
    if not price:
        return 0.0
    return (input_tokens / 1_000_000) * price["input"] + \
           (output_tokens / 1_000_000) * price["output"]
