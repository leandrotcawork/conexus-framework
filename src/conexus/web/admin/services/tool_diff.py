"""Estimate prompt-token + cost impact of adding a connector."""
from __future__ import annotations

from dataclasses import dataclass

_WORDS_PER_TOKEN = 0.75
_DEFAULT_USD_PER_1K_INPUT = 0.00015


@dataclass(frozen=True)
class ToolDiff:
    connector_name: str
    added_tools: int
    estimated_tokens: int
    estimated_cost_per_turn_usd: float


def _estimate_tokens(descriptions: dict[str, str]) -> int:
    words = sum(len(d.split()) for d in descriptions.values())
    schema_overhead = 30 * len(descriptions)
    return int(words / _WORDS_PER_TOKEN) + schema_overhead


def diff_for_connector(
    *, connector_name: str, new_tool_names: list[str],
    sample_descriptions: dict[str, str],
    cost_per_1k_input_usd: float = _DEFAULT_USD_PER_1K_INPUT,
) -> ToolDiff:
    tokens = _estimate_tokens(sample_descriptions)
    return ToolDiff(
        connector_name=connector_name,
        added_tools=len(new_tool_names),
        estimated_tokens=tokens,
        estimated_cost_per_turn_usd=round(tokens / 1000 * cost_per_1k_input_usd, 5),
    )
