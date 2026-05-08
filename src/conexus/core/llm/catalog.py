"""Model catalog — live /v1/models for capable providers, bundled catalog else.

Backed entirely by litellm primitives; no per-provider hand-rolled fetchers.
Caller maintenance is `pip install -U litellm` plus env-keys.
"""
from __future__ import annotations

import os
from functools import lru_cache

SUPPORTED_PROVIDERS: tuple[str, ...] = ("openai", "anthropic", "gemini", "deepseek", "groq")

# Providers where litellm.get_valid_models(check_provider_endpoint=True) probes /v1/models live.
_LIVE_CAPABLE: frozenset[str] = frozenset({"openai", "anthropic", "gemini"})

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
    """Call .cache_clear() when provider catalog or key changes."""
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
