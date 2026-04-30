"""Handoff — typed, versioned payload passed between agents in a team."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from conexus.core.trifecta.tags import DataClass


class Handoff(BaseModel):
    """Cross-agent message carrying payload + trifecta taint + hop accounting."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    from_agent: str
    to_agent: str
    payload: dict[str, Any] = Field(default_factory=dict)
    context_mode: Literal["full", "last_message", "summary"] = "summary"
    return_on: str | None = None
    hop_count: int = 0
    max_hops: int = 5
    tags: set[DataClass] = Field(default_factory=set)
    trust_boundary_cleared: bool = False

    def next_hop(self, to_agent: str) -> "Handoff":
        new_count = self.hop_count + 1
        if new_count > self.max_hops:
            raise ValueError(f"max_hops exceeded ({self.max_hops})")
        return self.model_copy(update={
            "to_agent": to_agent,
            "hop_count": new_count,
            "from_agent": self.to_agent,
        })
