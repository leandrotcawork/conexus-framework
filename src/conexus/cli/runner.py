"""Framework runtime builder — constructs AgentHandlerConfig from a SKILL.md path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from conexus.core.agent_handler import AgentHandlerConfig
from conexus.core.budget.cap_checker import BudgetCap
from conexus.core.config.skill_loader import parse_skill_file
from conexus.core.llm.router import LLMConfig, build_llm
from conexus.core.llm.usage_tracker import UsageTracker
from conexus.core.tools.schema_gen import generate_tool_schemas


@dataclass
class AgentRuntime:
    handler_cfg: AgentHandlerConfig
    tools_schema: list[dict]


def build_runtime(
    skill_path: str,
    *,
    tools_obj: Any,
    execute_tool: Callable[[str, dict], Awaitable[str]],
    tracker: UsageTracker,
    agent_name: str,
    system_prompt: str,
    cap: BudgetCap | None = None,
    cap_exceeded_msg: str = "Orçamento atingido.",
    fallback_msg: str = "Não consegui completar a tarefa.",
    max_turns: int = 6,
    progress_map: dict[str, str] | None = None,
    result_max_chars: int | None = None,
) -> AgentRuntime:
    """Parse skill file, build LLM, return AgentRuntime ready to hand to a bot."""
    skill = parse_skill_file(skill_path)

    llm_cfg = LLMConfig(
        provider=skill.frontmatter.llm.provider,
        model=skill.frontmatter.llm.model,
        temperature=skill.frontmatter.llm.temperature,
        fallback=[{"provider": f.provider, "model": f.model} for f in skill.frontmatter.llm.fallback],
    )
    llm = build_llm(llm_cfg, tracker, agent_name=agent_name)

    budget = BudgetCap(
        daily_usd=skill.frontmatter.budget.daily_usd,
        monthly_usd=skill.frontmatter.budget.monthly_usd,
        on_exceed=skill.frontmatter.budget.on_exceed,
    ) if skill.frontmatter.budget else cap

    tools_schema = generate_tool_schemas(type(tools_obj), skill.frontmatter.tools)

    handler_cfg = AgentHandlerConfig(
        name=agent_name,
        llm=llm,
        tools_schema=tools_schema,
        execute_tool=execute_tool,
        system_prompt=system_prompt,
        max_turns=max_turns,
        cap=budget,
        cap_exceeded_msg=cap_exceeded_msg,
        include_facts=True,
        fallback_msg=fallback_msg,
        **({"progress_map": progress_map} if progress_map else {}),
        **({"result_max_chars": result_max_chars} if result_max_chars else {}),
    )

    return AgentRuntime(handler_cfg=handler_cfg, tools_schema=tools_schema)
