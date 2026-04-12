"""LLM router: provider-agnostic LLM calls via LiteLLM with usage tracking and fallback.

Every agent gets its LLM from `build_llm(config, tracker, agent_name)`. The
returned callable wraps `litellm.completion` and records token usage per call,
tagging each with the current context (via ContextVar).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from core.llm.context_tag import current_context
from core.llm.usage_tracker import UsageTracker


@dataclass
class LLMConfig:
    provider: str
    model: str
    temperature: float = 0.4
    fallback: list[dict] | None = None  # list of {provider, model}


class TrackedLLM:
    """Thin callable wrapper around litellm.completion."""

    def __init__(self, config: LLMConfig, tracker: UsageTracker, agent_name: str):
        self.config = config
        self.tracker = tracker
        self.agent_name = agent_name

    def complete(self, messages: list[dict], **kwargs) -> str:
        """Send a completion request; return the assistant text. Logs usage per call."""
        import litellm

        providers_to_try: list[tuple[str, str]] = [(self.config.provider, self.config.model)]
        if self.config.fallback:
            providers_to_try += [(f["provider"], f["model"]) for f in self.config.fallback]

        last_error: Exception | None = None
        for provider, model in providers_to_try:
            full_model = f"{provider}/{model}"
            start = time.monotonic()
            try:
                resp = litellm.completion(
                    model=full_model,
                    messages=messages,
                    temperature=self.config.temperature,
                    **kwargs,
                )
                duration_ms = int((time.monotonic() - start) * 1000)

                usage = resp.get("usage") if isinstance(resp, dict) else resp.usage
                input_tokens = getattr(usage, "prompt_tokens", 0) or usage.get("prompt_tokens", 0)
                output_tokens = getattr(usage, "completion_tokens", 0) or usage.get("completion_tokens", 0)

                self.tracker.log_call(
                    agent_name=self.agent_name,
                    provider=provider,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    context=current_context(),
                    duration_ms=duration_ms,
                )

                choice = resp["choices"][0] if isinstance(resp, dict) else resp.choices[0]
                return choice["message"]["content"] if isinstance(choice, dict) else choice.message.content

            except Exception as e:
                last_error = e
                self.tracker.log_call(
                    agent_name=self.agent_name,
                    provider=provider,
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    context=current_context(),
                    duration_ms=int((time.monotonic() - start) * 1000),
                    error=str(e)[:500],
                )
                continue

        assert last_error is not None
        raise last_error


def build_llm(config: LLMConfig, tracker: UsageTracker, agent_name: str) -> TrackedLLM:
    return TrackedLLM(config, tracker, agent_name)
