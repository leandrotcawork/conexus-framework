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


@lru_cache(maxsize=1)
def list_providers() -> list[str]:
    """Call .cache_clear() when API key env vars change."""
    return [p for p in SUPPORTED_PROVIDERS if os.environ.get(_ENV_KEY[p])]


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


def llm_options() -> dict[str, list[str]]:
    """Compat shim — same shape as old pricing.llm_options()."""
    return {p: list_models(p) for p in list_providers()}


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
