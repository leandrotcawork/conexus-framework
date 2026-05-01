"""Builds the delegate_to_<agent> LLM tool schema for a team registry.

When the LLM emits a tool call starting with `delegate_to_`, the loop builds
a Handoff and yields control to the named sibling agent.
"""
from __future__ import annotations
from typing import Any
from conexus.core.team.team_registry import TeamRegistry

DELEGATE_PREFIX = "delegate_to_"
_VALID_MODES = ("full", "last_message", "summary")


def build_delegate_schemas(registry: TeamRegistry, current_agent: str) -> list[dict]:
    schemas: list[dict] = []
    for member in registry.members:
        if member == current_agent:
            continue
        schemas.append({
            "type": "function",
            "function": {
                "name": f"{DELEGATE_PREFIX}{member}",
                "description": f"Delegate sub-task to teammate '{member}'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "object",
                            "description": "Free-form payload describing the sub-task.",
                        },
                        "context_mode": {
                            "type": "string",
                            "enum": list(_VALID_MODES),
                            "description": "How much transcript to forward (default: summary).",
                        },
                        "return_on": {
                            "type": "string",
                            "description": "Target agent's reply containing this text returns control.",
                        },
                    },
                    "required": ["task"],
                },
            },
        })
    return schemas


def parse_delegate_call(
    tool_name: str,
    args: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Returns (target_agent, payload, optional_overrides). Raises ValueError on bad input."""
    if not tool_name.startswith(DELEGATE_PREFIX):
        raise ValueError(f"not a delegate call: {tool_name}")
    target = tool_name[len(DELEGATE_PREFIX):]
    if not target:
        raise ValueError("delegate target empty")
    if "task" not in args:
        raise ValueError("delegate call missing required 'task' field")
    payload = {"task": args["task"]}
    opts: dict[str, Any] = {}
    if "context_mode" in args:
        if args["context_mode"] not in _VALID_MODES:
            raise ValueError(f"invalid context_mode: {args['context_mode']}")
        opts["context_mode"] = args["context_mode"]
    if "return_on" in args:
        opts["return_on"] = str(args["return_on"])
    return target, payload, opts
