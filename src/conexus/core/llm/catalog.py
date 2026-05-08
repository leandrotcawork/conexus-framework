"""Model catalog — live /v1/models where possible, bundled litellm catalog else.

Priority per provider:
  1. litellm.get_valid_models(check_provider_endpoint=True) — openai/anthropic/gemini.
  2. Direct GET /models probe — deepseek/groq (litellm doesn't probe these live).
  3. litellm bundled model_cost catalog (refreshes on `pip install -U litellm`).

Caller maintenance: keep litellm up-to-date + supply API key env vars.
"""
from __future__ import annotations

import json
import os
import urllib.request
from functools import lru_cache

# All providers surfaced in Studio — simple API key, chat-capable, actively maintained.
# Allowlist beats blocklist: litellm has 100+ entries including legacy/obscure providers.
ALL_PROVIDERS: tuple[str, ...] = (
    "openai", "anthropic", "gemini", "deepseek", "groq",
    "mistral", "cohere", "together_ai", "perplexity", "fireworks_ai",
    "xai", "huggingface", "replicate", "openrouter", "anyscale",
    "ollama", "databricks", "predibase",
)

SUPPORTED_PROVIDERS: tuple[str, ...] = ("openai", "anthropic", "gemini", "deepseek", "groq")

# Providers where litellm probes /v1/models live.
_LIVE_CAPABLE: frozenset[str] = frozenset({"openai", "anthropic", "gemini"})

# Providers litellm can't probe — we call their /models directly.
_DIRECT_LIVE: dict[str, tuple[str, str]] = {
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com/models"),
    "groq":     ("GROQ_API_KEY",     "https://api.groq.com/openai/v1/models"),
}

_ENV_KEY: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "groq": "GROQ_API_KEY",
}

_EXCLUDE: tuple[str, ...] = (
    "audio", "realtime", "tts", "search", "native", "live", "robotics",
    "container", "lyria", "learnlm", "image", "embedding", "ft:", "video",
    "vision", "ocr", "computer-use", "customtools",
)


def all_providers() -> list[str]:
    """All reasonable providers — simple API key, chat-capable, actively maintained."""
    return list(ALL_PROVIDERS)


@lru_cache(maxsize=1)
def list_providers() -> list[str]:
    """Configured-only subset — providers with API key present in env."""
    return [p for p in ALL_PROVIDERS if os.environ.get(_ENV_KEY.get(p, f"{p.upper()}_API_KEY"))]


@lru_cache(maxsize=8)
def list_models(provider: str) -> list[str]:
    """Live probe → direct probe → catalog. Call .cache_clear() on key change."""
    import litellm
    if provider in _LIVE_CAPABLE:
        try:
            live = litellm.get_valid_models(
                check_provider_endpoint=True,
                custom_llm_provider=provider,
            )
            if live:
                return sorted(_filter_chat(live))
        except Exception:
            pass
    if provider in _DIRECT_LIVE:
        live = _direct_live_models(provider)
        if live:
            return sorted(_filter_chat(live))
    return sorted(_filter_chat(_catalog_models(provider)))


def get_info(model: str) -> dict:
    import litellm
    try:
        return dict(litellm.get_model_info(model))
    except Exception:
        return {}


def llm_options(configured_only: bool = False) -> dict[str, list[str]]:
    """Return {provider: [models]}. configured_only=True filters to key-present providers."""
    providers = list_providers() if configured_only else all_providers()
    return {p: list_models(p) for p in providers}


def configured_providers() -> set[str]:
    """Set of providers that have an API key in env."""
    return set(list_providers())


def _direct_live_models(provider: str) -> list[str]:
    """GET /models from provider API. Returns [] on any failure."""
    env_key, url = _DIRECT_LIVE[provider]
    key = os.environ.get(env_key)
    if not key:
        return []
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        return [m["id"] for m in data.get("data", [])]
    except Exception:
        return []


def _catalog_models(provider: str) -> list[str]:
    import litellm
    out: list[str] = []
    seen: set[str] = set()
    for k, info in litellm.model_cost.items():
        if info.get("mode") != "chat":
            continue
        if "/" in k:
            p, m = k.split("/", 1)
            if "/" in m:
                continue
        else:
            p, m = info.get("litellm_provider", ""), k
        if p != provider or m in seen:
            continue
        seen.add(m)
        out.append(m)
    return out


def _filter_chat(models: list[str]) -> list[str]:
    return [m for m in models if not any(b in m.lower() for b in _EXCLUDE)]
