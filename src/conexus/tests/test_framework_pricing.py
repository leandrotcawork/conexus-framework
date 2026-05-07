from unittest.mock import patch

import pytest

from conexus.core.llm.pricing import compute_cost, llm_options, USD_TO_BRL


def test_llm_options_has_required_providers():
    options = llm_options()
    assert set(options.keys()) >= {"openai", "anthropic", "gemini"}


def test_llm_options_models_are_strings():
    options = llm_options()
    for provider, models in options.items():
        assert isinstance(models, list)
        assert all(isinstance(m, str) for m in models)
        assert len(models) > 0, f"{provider} has no models"


def test_llm_options_no_excluded_keywords():
    excluded = ("audio", "realtime", "tts", "embedding", "image", "vision", "video")
    options = llm_options()
    for provider, models in options.items():
        for model in models:
            lower = model.lower()
            for ex in excluded:
                assert ex not in lower, f"{provider}/{model} contains excluded keyword '{ex}'"


def test_compute_cost_returns_float():
    cost = compute_cost("gemini/gemini-2.0-flash", 1_000_000, 1_000_000)
    assert isinstance(cost, float)
    assert cost > 0


def test_compute_cost_mocked_values():
    """Verify compute_cost sums input+output costs from litellm."""
    with patch("litellm.cost_per_token", return_value=(0.075, 0.300)):
        cost = compute_cost("gemini/gemini-2.0-flash", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.375, rel=1e-6)


def test_compute_cost_unknown_model_returns_zero():
    assert compute_cost("fake/model-does-not-exist", 100, 100) == 0.0


def test_usd_to_brl_is_positive():
    assert USD_TO_BRL > 0
