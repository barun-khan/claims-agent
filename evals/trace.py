from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class AgentTrace:
    """Everything the runner needs to score one case.

    Any agent -- stub, local, Foundry-hosted -- returns this shape. That is
    what lets you swap the agent without touching a single metric.
    """
    case_id: str
    output: dict | None = None        # parsed ClaimDecision, or None if unparseable
    raw_output: str = ""
    tool_calls: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    error: str | None = None