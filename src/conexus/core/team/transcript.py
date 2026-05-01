"""Per-edge transcript trimming for cross-agent handoffs."""
from __future__ import annotations


def trim_transcript(messages: list[dict], mode: str) -> list[dict]:
    """Return a trimmed copy of `messages` per `context_mode`.

    Modes:
      full          — full copy.
      last_message  — only the last non-system message.
      summary       — single system message marking N prior turns.
    """
    if mode == "full":
        return list(messages)
    if mode == "last_message":
        for m in reversed(messages):
            if m.get("role") != "system":
                return [dict(m)]
        return []
    if mode == "summary":
        n = len(messages)
        return [{
            "role": "system",
            "content": f"Transcript summary: {n} prior message(s) elided by handoff context_mode=summary.",
        }]
    raise ValueError(f"invalid context_mode: {mode}")
