"""LLM-backed summarizer for conversation history compaction."""
from __future__ import annotations

from typing import Callable, Sequence


SUMMARIZER_PROMPT_PT = (
    "Atualize o resumo abaixo incorporando as novas mensagens. "
    "Mantenha fatos sobre o usuário, decisões tomadas, e tarefas pendentes. "
    "Limite: {budget} tokens. Responda apenas com o resumo, sem prefácios.\n\n"
    "Resumo atual:\n{old_summary}\n\nNovas mensagens:\n{new_messages}"
)


def format_messages(messages: Sequence[dict]) -> str:
    return "\n".join(f"[{m['role']}] {m['content']}" for m in messages)


def make_summarizer(llm_call: Callable[[str], str], budget_tokens: int) -> Callable[[str | None, list[dict]], str]:
    """Return a summarize_fn(old_summary, new_messages) -> new_summary."""
    def summarize(old_summary: str | None, new_messages: list[dict]) -> str:
        prompt = SUMMARIZER_PROMPT_PT.format(
            budget=budget_tokens,
            old_summary=old_summary or "(vazio)",
            new_messages=format_messages(new_messages),
        )
        return llm_call(prompt).strip()
    return summarize
