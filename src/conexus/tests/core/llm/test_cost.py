from types import SimpleNamespace
from conexus.core.llm.cost import cost_from_response


def test_prefers_hidden_params():
    resp = SimpleNamespace(_hidden_params={"response_cost": 0.012345})
    assert cost_from_response(resp) == 0.012345


def test_fallback_to_cost_per_token(monkeypatch):
    resp = SimpleNamespace(
        _hidden_params={},
        model="openai/gpt-4o-mini",
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
    )
    monkeypatch.setattr("litellm.cost_per_token", lambda **kw: (0.001, 0.002))
    assert cost_from_response(resp) == 0.003


def test_returns_zero_on_failure():
    resp = SimpleNamespace(_hidden_params={}, model="bad", usage=None)
    assert cost_from_response(resp) == 0.0
