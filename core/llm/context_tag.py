"""ContextVar-based context tag propagation for LLM call attribution."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_current_context: ContextVar[str] = ContextVar("llm_context", default="unknown")


def current_context() -> str:
    return _current_context.get()


@contextmanager
def set_context(tag: str):
    token = _current_context.set(tag)
    try:
        yield
    finally:
        _current_context.reset(token)
