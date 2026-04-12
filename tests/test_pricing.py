import pytest

from core.llm.pricing import PRICING, compute_cost, USD_TO_BRL


def test_pricing_table_has_required_models():
    required = {
        "gemini/gemini-2.0-flash",
        "openai/gpt-4o-mini",
        "anthropic/claude-haiku-4-5",
        "deepseek/deepseek-chat",
    }
    assert required.issubset(PRICING.keys())


def test_compute_cost_gemini_flash():
    # 1M input tokens at $0.075 + 1M output tokens at $0.30 = $0.375
    cost = compute_cost("gemini/gemini-2.0-flash", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.375, rel=1e-6)


def test_compute_cost_unknown_model_returns_zero():
    assert compute_cost("fake/model", 100, 100) == 0.0


def test_usd_to_brl_is_positive():
    assert USD_TO_BRL > 0
