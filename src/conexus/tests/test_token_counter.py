# src/conexus/tests/test_token_counter.py
from unittest.mock import patch
from conexus.web.admin.services.token_counter import count_schema_tokens


def test_returns_zero_for_empty():
    assert count_schema_tokens([], model="gpt-4o-mini") == 0


def test_returns_token_count_for_schemas():
    schemas = [{"name": "ping", "description": "say hi", "parameters": {"type": "object"}}]
    with patch("litellm.token_counter", return_value=12):
        n = count_schema_tokens(schemas, model="gpt-4o-mini")
    assert n == 12


def test_falls_back_to_zero_on_error():
    schemas = [{"name": "x"}]
    with patch("litellm.token_counter", side_effect=RuntimeError("boom")):
        assert count_schema_tokens(schemas, model="gpt-4o-mini") == 0
