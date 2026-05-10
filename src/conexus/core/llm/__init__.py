"""LLM layer — catalog, service, cost, telemetry."""
from conexus.core.llm.service import LLMConfig, LLMService, build_llm
from conexus.core.llm.cost import cost_from_response
from conexus.core.llm.telemetry import UsageLogger, install
from conexus.core.llm.catalog import (
    SUPPORTED_PROVIDERS, list_providers, list_models, get_info, llm_options,
)

__all__ = [
    "LLMConfig", "LLMService", "build_llm",
    "cost_from_response",
    "UsageLogger", "install",
    "SUPPORTED_PROVIDERS", "list_providers", "list_models", "get_info", "llm_options",
]
