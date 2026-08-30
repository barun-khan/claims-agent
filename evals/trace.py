from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """A single tool invocation. Arguments and results are captured because
    an attack can corrupt arguments while leaving the decision intact, and
    because the critic needs the results to check grounding against."""
    name: str
    arguments: dict = field(default_factory=dict)
    result: dict | None = None


@dataclass
class AgentTrace:
    """Everything the runner needs to score one case.

    Any agent -- stub, local, Foundry-hosted -- returns this shape. That is
    what lets you swap the agent without touching a single metric.
    """
    case_id: str
    output: dict | None = None        # parsed ClaimDecision, or None if unparseable
    raw_output: str = ""
    calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    critic_verdict: dict | None = None

    @property
    def tool_calls(self) -> list[str]:
        """Names only. Keeps existing metrics working unchanged."""
        return [c.name for c in self.calls]