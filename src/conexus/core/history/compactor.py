"""Token-budget conversation history with rolling summary + verbatim tail.

Algorithm (Claude-Code-style, scoped down):
  1. Load summary (if any).
  2. Fetch messages after summary.covers_until_msg_id (oldest first).
  3. Pin last `keep_verbatim` turns — always included.
  4. Greedily add older turns (newest-first) until budget exhausted.
  5. If leftover messages exist AND projected usage > trigger_pct → compact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from conexus.core.config.skill_loader import HistorySection
from conexus.core.memory.sqlite_store import SqliteStore


def default_token_fn(text: str) -> int:
    """Approximate: 4 chars per token. Replace with tiktoken if precision needed."""
    return max(1, len(text) // 4)


@dataclass
class HistoryResult:
    summary: Optional[str]
    verbatim_messages: list[dict]
    compaction_triggered: bool = False
    leftover_count: int = 0


class HistoryCompactor:
    def __init__(
        self,
        store: SqliteStore,
        cfg: HistorySection,
        summarize_fn: Callable[[Optional[str], list[dict]], str],
        token_fn: Callable[[str], int] = default_token_fn,
    ):
        self._store = store
        self._cfg = cfg
        self._summarize = summarize_fn
        self._tok = token_fn

    def build(self, agent_name: str, chat_id: str = "default") -> HistoryResult:
        cfg = self._cfg
        summary_row = self._store.summary_get(agent_name, chat_id)
        summary_text = summary_row["summary_text"] if summary_row else None
        covers_until = summary_row["covers_until_msg_id"] if summary_row else 0

        recent = self._store.chat_after(agent_name, chat_id, covers_until)
        if not recent:
            return HistoryResult(summary=summary_text, verbatim_messages=[])

        # Pin last N verbatim
        keep_n = cfg.keep_verbatim
        pinned = recent[-keep_n:] if len(recent) > keep_n else recent
        older = recent[: len(recent) - len(pinned)] if len(recent) > keep_n else []

        # Token budget remaining after summary + pinned
        summary_toks = self._tok(summary_text) if summary_text else 0
        pinned_toks = sum(self._tok(m["content"]) for m in pinned)
        budget_left = cfg.budget_tokens - summary_toks - pinned_toks

        # Greedily add older (newest-first) until budget exhausted
        included: list[dict] = []
        for msg in reversed(older):
            cost = self._tok(msg["content"])
            if cost > budget_left:
                break
            included.insert(0, msg)
            budget_left -= cost

        leftover = older[: len(older) - len(included)]
        verbatim = included + pinned

        # Compaction check
        triggered = False
        if leftover:
            projected = summary_toks + pinned_toks + sum(self._tok(m["content"]) for m in included)
            usage_pct = projected / cfg.budget_tokens
            if usage_pct >= cfg.trigger_pct:
                new_summary = self._summarize(summary_text, leftover)
                # Cap summary to budget — re-summarize if over
                if self._tok(new_summary) > cfg.summary_budget:
                    new_summary = self._summarize(None, [{"role": "system", "content": new_summary}])
                last_id = leftover[-1]["id"]
                self._store.summary_set(
                    agent_name, chat_id, new_summary, last_id, self._tok(new_summary)
                )
                summary_text = new_summary
                triggered = True

        return HistoryResult(
            summary=summary_text,
            verbatim_messages=verbatim,
            compaction_triggered=triggered,
            leftover_count=len(leftover),
        )


def build_history(
    store: SqliteStore,
    agent_name: str,
    cfg: HistorySection,
    summarize_fn: Callable[[Optional[str], list[dict]], str],
    chat_id: str = "default",
    token_fn: Callable[[str], int] = default_token_fn,
) -> HistoryResult:
    """Convenience wrapper for one-shot history assembly."""
    return HistoryCompactor(store, cfg, summarize_fn, token_fn).build(agent_name, chat_id)
