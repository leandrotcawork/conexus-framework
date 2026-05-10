"""UsageLogger — single litellm CustomLogger that persists every call to llm_usage."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from litellm.integrations.custom_logger import CustomLogger

from conexus.core.llm.context_tag import current_context
from conexus.core.llm.cost import cost_from_response
from conexus.core.memory.sqlite_store import SqliteStore


class UsageLogger(CustomLogger):
    def __init__(self, store: SqliteStore):
        super().__init__()
        self.store = store

    async def async_log_success_event(self, kwargs: dict, response_obj: Any, start_time, end_time):
        self._record(kwargs, response_obj, start_time, end_time, error=None)

    async def async_log_failure_event(self, kwargs: dict, response_obj: Any, start_time, end_time):
        err = kwargs.get("exception") or response_obj
        self._record(kwargs, response_obj, start_time, end_time, error=str(err)[:500])

    def _record(self, kwargs, resp, start, end, *, error: str | None) -> None:
        # LiteLLM Router places caller metadata at kwargs["litellm_params"]["metadata"];
        # bare litellm.completion places it at kwargs["metadata"]. Check both.
        meta = (
            (kwargs.get("litellm_params") or {}).get("metadata")
            or kwargs.get("metadata")
            or {}
        )
        agent_name = meta.get("agent_name")
        if not agent_name:
            return  # Skip non-Conexus calls (e.g., diagnostic litellm probes).
        full_model = kwargs.get("model", "")
        if "/" in full_model:
            provider, _, model = full_model.partition("/")
        else:
            provider, model = "", full_model
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "prompt_tokens", 0) if usage else 0
        out_tok = getattr(usage, "completion_tokens", 0) if usage else 0
        cost = cost_from_response(resp) if resp is not None else 0.0
        duration_ms = int((end - start).total_seconds() * 1000) if start and end else None
        with self.store.connect() as conn:
            conn.execute(
                """INSERT INTO llm_usage
                   (ts, agent_name, provider, model, input_tokens, output_tokens,
                    cost_usd, context, duration_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (datetime.now(timezone.utc).isoformat(),
                 agent_name, provider, model,
                 in_tok, out_tok, cost, current_context(), duration_ms, error),
            )
            conn.commit()


def install(store: SqliteStore) -> UsageLogger:
    import litellm
    existing = [c for c in (litellm.callbacks or []) if not isinstance(c, UsageLogger)]
    logger = UsageLogger(store)
    litellm.callbacks = existing + [logger]
    return logger
