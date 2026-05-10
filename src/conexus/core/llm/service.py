"""LLMService — single entry point wrapping litellm.Router.

Router owns retry, fallback, cooldown. Telemetry hooks in via litellm.callbacks
(see telemetry.install). Caller wires only LLMConfig + agent_name.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from litellm import Router
import copy


def _apply_cache_control(
    messages: list[dict], kw: dict
) -> tuple[list[dict], dict]:
    """Attach Anthropic cache_control markers to system message + last tool.

    Creates shallow copies — does not mutate caller's data.
    """
    messages = list(messages)
    if messages and messages[0].get("role") == "system":
        sys_msg = dict(messages[0])
        content = sys_msg["content"]
        if isinstance(content, str):
            sys_msg["content"] = [
                {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
            ]
        elif isinstance(content, list) and content:
            blocks = list(content)
            last = dict(blocks[-1])
            last["cache_control"] = {"type": "ephemeral"}
            blocks[-1] = last
            sys_msg["content"] = blocks
        messages[0] = sys_msg

    tools = kw.get("tools")
    if tools:
        kw = dict(kw)
        tools = list(tools)
        last_tool = copy.copy(tools[-1])
        last_tool["cache_control"] = {"type": "ephemeral"}
        tools[-1] = last_tool
        kw["tools"] = tools

    return messages, kw


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    temperature: float = 0.4
    fallback: list[dict] | None = None  # [{provider, model}, ...]


class LLMService:
    def __init__(self, config: LLMConfig, agent_name: str):
        self.config = config
        self.agent_name = agent_name
        self._router = Router(
            model_list=self._build_model_list(),
            fallbacks=self._build_fallbacks(),
            num_retries=3,
            cooldown_time=60,
            timeout=60,
            retry_after=5,
        )

    def _build_model_list(self) -> list[dict]:
        cfg = self.config
        entries = [{
            "model_name": "primary",
            "litellm_params": {
                "model": f"{cfg.provider}/{cfg.model}",
                "temperature": cfg.temperature,
            },
        }]
        for i, fb in enumerate(cfg.fallback or []):
            entries.append({
                "model_name": f"fb{i}",
                "litellm_params": {
                    "model": f"{fb['provider']}/{fb['model']}",
                    "temperature": cfg.temperature,
                },
            })
        return entries

    def _build_fallbacks(self) -> list[dict]:
        n = len(self.config.fallback or [])
        return [{"primary": [f"fb{i}" for i in range(n)]}] if n else []

    async def acompletion(self, messages: list[dict], *, cache_control: bool = False, **kw) -> Any:
        meta = dict(kw.pop("metadata", {}) or {})
        meta["agent_name"] = self.agent_name
        if cache_control:
            messages, kw = _apply_cache_control(messages, kw)
        return await self._router.acompletion(
            model="primary", messages=messages, metadata=meta, **kw,
        )

    async def acall(self, messages: list[dict], **kw) -> tuple[Any, str]:
        """Compat shim: returns (resp, full_model) matching old TrackedLLM.acall()."""
        resp = await self.acompletion(messages, **kw)
        full_model = f"{self.config.provider}/{self.config.model}"
        return resp, full_model

    async def acomplete_text(self, messages: list[dict], **kw) -> str:
        resp = await self.acompletion(messages, **kw)
        return resp.choices[0].message.content


def build_llm(config: LLMConfig, agent_name: str) -> LLMService:
    return LLMService(config, agent_name)
