from unittest.mock import patch

import pytest

from conexus.core.llm.catalog import llm_options
from conexus.core.llm.cost import cost_from_response


def test_llm_options_has_providers(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    options = llm_options(configured_only=True)
    assert isinstance(options, dict)
    assert len(options) > 0
    # At least one provider should be available (test environment sets DEEPSEEK_API_KEY)
    for provider_models in options.values():
        assert isinstance(provider_models, list)
        assert len(provider_models) > 0


def test_llm_options_models_are_strings(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    options = llm_options(configured_only=True)
    for provider, models in options.items():
        assert isinstance(models, list)
        assert all(isinstance(m, str) for m in models)
        assert len(models) > 0, f"{provider} has no models"


def test_llm_options_no_excluded_keywords():
    excluded = ("audio", "realtime", "tts", "embedding", "image", "vision", "video")
    options = llm_options(configured_only=True)
    for provider, models in options.items():
        for model in models:
            lower = model.lower()
            for ex in excluded:
                assert ex not in lower, f"{provider}/{model} contains excluded keyword '{ex}'"


def test_cost_from_response_with_hidden_params():
    """Verify cost_from_response uses _hidden_params if available."""
    class MockResp:
        _hidden_params = {"response_cost": 0.50}
    resp = MockResp()
    cost = cost_from_response(resp)
    assert cost == 0.50


def test_cost_from_response_with_usage():
    """Verify cost_from_response falls back to cost_per_token."""
    class MockUsage:
        prompt_tokens = 1_000_000
        completion_tokens = 1_000_000
    class MockResp:
        _hidden_params = None
        usage = MockUsage()
        model = "gemini/gemini-2.0-flash"
    resp = MockResp()
    with patch("litellm.cost_per_token", return_value=(0.075, 0.300)):
        cost = cost_from_response(resp)
    assert cost == pytest.approx(0.375, rel=1e-6)


def test_cost_from_response_no_usage_returns_zero():
    """Verify cost_from_response returns 0 when no usage is present."""
    class MockResp:
        _hidden_params = None
        usage = None
    resp = MockResp()
    cost = cost_from_response(resp)
    assert cost == 0.0
