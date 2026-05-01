"""transcript trim modes: full | last_message | summary."""
from __future__ import annotations
import pytest
from conexus.core.team.transcript import trim_transcript


def _msgs():
    return [
        {"role": "system", "content": "You are ana."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "research X"},
        {"role": "assistant", "content": "found X"},
    ]


def test_full_returns_all():
    out = trim_transcript(_msgs(), "full")
    assert len(out) == 5
    assert out is not _msgs()  # must be a copy


def test_last_message_returns_only_last_non_system():
    out = trim_transcript(_msgs(), "last_message")
    assert len(out) == 1
    assert out[0]["role"] == "assistant"
    assert out[0]["content"] == "found X"


def test_summary_returns_compact_marker():
    out = trim_transcript(_msgs(), "summary")
    assert len(out) == 1
    assert out[0]["role"] == "system"
    assert "transcript summary" in out[0]["content"].lower()
    assert "5 prior message" in out[0]["content"]


def test_empty_input():
    assert trim_transcript([], "full") == []
    assert trim_transcript([], "last_message") == []
    out = trim_transcript([], "summary")
    assert len(out) == 1


def test_invalid_mode():
    with pytest.raises(ValueError):
        trim_transcript(_msgs(), "bogus")
