import pytest
from unittest.mock import AsyncMock, patch
from conexus.core.llm.service import LLMConfig, LLMService, build_llm


def test_config_defaults():
    c = LLMConfig(provider="deepseek", model="deepseek-v4-flash")
    assert c.temperature == 0.4
    assert c.fallback is None


def test_build_model_list_with_fallback():
    svc = LLMService(
        LLMConfig(
            provider="deepseek", model="deepseek-v4-flash",
            fallback=[{"provider": "anthropic", "model": "claude-haiku-4-5"}],
        ),
        agent_name="t",
    )
    ml = svc._build_model_list()
    assert ml[0]["litellm_params"]["model"] == "deepseek/deepseek-v4-flash"
    assert ml[1]["litellm_params"]["model"] == "anthropic/claude-haiku-4-5"
    assert ml[1]["model_name"] == "fb0"


def test_build_fallbacks_empty_when_none():
    svc = LLMService(LLMConfig(provider="deepseek", model="deepseek-v4-flash"), agent_name="t")
    assert svc._build_fallbacks() == []


def test_build_fallbacks_chains_primary_to_fallback_names():
    svc = LLMService(
        LLMConfig(
            provider="a", model="m",
            fallback=[{"provider": "b", "model": "m"}, {"provider": "c", "model": "m"}],
        ),
        agent_name="t",
    )
    assert svc._build_fallbacks() == [{"primary": ["fb0", "fb1"]}]


@pytest.mark.asyncio
async def test_acomplete_text_returns_string():
    fake_resp = AsyncMock()
    fake_resp.choices = [type("C", (), {"message": type("M", (), {"content": "ola"})()})()]
    with patch("litellm.Router.acompletion", new_callable=AsyncMock, return_value=fake_resp):
        svc = LLMService(LLMConfig(provider="deepseek", model="deepseek-v4-flash"), agent_name="t")
        out = await svc.acomplete_text([{"role": "user", "content": "hi"}])
    assert out == "ola"


@pytest.mark.asyncio
async def test_acompletion_passes_agent_name_in_metadata():
    fake_resp = AsyncMock()
    fake_resp.choices = [type("C", (), {"message": type("M", (), {"content": "x"})()})()]
    captured = {}

    async def fake_router_acompletion(self, **kw):
        captured.update(kw)
        return fake_resp

    with patch("litellm.Router.acompletion", new=fake_router_acompletion):
        svc = LLMService(LLMConfig(provider="deepseek", model="deepseek-v4-flash"), agent_name="ana")
        await svc.acomplete_text([{"role": "user", "content": "hi"}])
    assert captured["metadata"]["agent_name"] == "ana"


@pytest.mark.asyncio
async def test_router_falls_back_on_rate_limit():
    import litellm
    svc = LLMService(
        LLMConfig(
            provider="deepseek", model="deepseek-v4-flash",
            fallback=[{"provider": "anthropic", "model": "claude-haiku-4-5"}],
        ),
        agent_name="t",
    )
    assert svc._build_fallbacks() == [{"primary": ["fb0"]}]
    calls = []

    async def fake(self, **kw):
        calls.append(kw["model"])
        if len(calls) == 1:
            raise litellm.exceptions.RateLimitError(
                message="rate", llm_provider="deepseek", model="deepseek-v4-flash"
            )
        return AsyncMock(choices=[type("C", (), {"message": type("M", (), {"content": "fb"})()})()])

    with patch("litellm.Router.acompletion", new=fake):
        try:
            await svc.acomplete_text([{"role": "user", "content": "hi"}])
        except litellm.exceptions.RateLimitError:
            pass
    assert calls and calls[0] == "primary"


def test_build_llm_returns_service():
    cfg = LLMConfig(provider="deepseek", model="deepseek-v4-flash")
    assert isinstance(build_llm(cfg, "t"), LLMService)
