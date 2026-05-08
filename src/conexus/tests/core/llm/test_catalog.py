"""Catalog tests — live probe + bundled fallback."""
from __future__ import annotations
import os
import pytest
from unittest.mock import patch
from conexus.core.llm import catalog


@pytest.fixture(autouse=True)
def _clear_catalog_caches():
    catalog.list_providers.cache_clear()
    catalog.list_models.cache_clear()
    yield
    catalog.list_providers.cache_clear()
    catalog.list_models.cache_clear()


def test_supported_providers_constant():
    assert catalog.SUPPORTED_PROVIDERS == ("openai", "anthropic", "gemini", "deepseek", "groq")


def test_list_providers_filters_by_env(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    assert catalog.list_providers() == ["deepseek"]


def test_list_models_uses_live_for_capable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    with patch("litellm.get_valid_models", return_value=["gpt-4o", "gpt-4o-mini"]) as m:
        models = catalog.list_models("openai")
    m.assert_called_once_with(check_provider_endpoint=True, custom_llm_provider="openai")
    assert "gpt-4o" in models


def test_list_models_falls_back_to_catalog_for_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    models = catalog.list_models("groq")
    assert isinstance(models, list)
    assert len(models) > 0
    assert all("audio" not in m for m in models)


def test_filter_chat_drops_specialized():
    raw = ["gpt-4o", "whisper-1-audio", "tts-1", "text-embedding-3-small"]
    filtered = catalog._filter_chat(raw)
    assert filtered == ["gpt-4o"]


def test_get_info_returns_dict_or_empty():
    info = catalog.get_info("gpt-4o")
    assert isinstance(info, dict) and len(info) > 0
    bogus = catalog.get_info("does-not-exist-xyz")
    assert bogus == {}


def test_llm_options_shape(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    opts = catalog.llm_options()
    assert "deepseek" in opts
    assert isinstance(opts["deepseek"], list)
