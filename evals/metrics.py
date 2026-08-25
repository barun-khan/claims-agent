from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from evals.trace import AgentTrace


@dataclass
class Metric:
    name: str
    fn: Callable[[AgentTrace, dict], float]

    def score(self, trace: AgentTrace, expected: dict) -> float:
        try:
            return float(self.fn(trace, expected))
        except Exception:
            return 0.0


def _schema_validity(trace: AgentTrace, expected: dict) -> float:
    return 1.0 if trace.output is not None and trace.error is None else 0.0


def _decision_match(trace: AgentTrace, expected: dict) -> float:
    if trace.output is None:
        return 0.0
    return 1.0 if trace.output.get("decision") == expected["decision"] else 0.0


def _reason_code_match(trace: AgentTrace, expected: dict) -> float:
    if trace.output is None:
        return 0.0
    return 1.0 if trace.output.get("reason") == expected["reason"] else 0.0


def _clause_precision(trace: AgentTrace, expected: dict) -> float:
    """Of the clauses the agent cited, how many actually apply?

    Precision, not recall, on purpose: an agent that cites every clause in the
    policy would score perfect recall while being useless.
    """
    if trace.output is None:
        return 0.0
    predicted = set(trace.output.get("clauses") or [])
    if not predicted:
        return 0.0
    return len(predicted & set(expected["clauses"])) / len(predicted)


def _tool_call_accuracy(trace: AgentTrace, expected: dict) -> float:
    return 1.0 if set(trace.tool_calls) == set(expected.get("_tools", [])) else 0.0


def is_false_approval(trace: AgentTrace, expected: dict) -> bool:
    """Approved when the truth was deny. Money leaves the building.

    Tracked separately from the goodness metrics because its gate is a
    ceiling, not a floor.
    """
    if trace.output is None:
        return False
    return trace.output.get("decision") == "approve" and expected["decision"] == "deny"


METRICS: list[Metric] = [
    Metric("schema_validity", _schema_validity),
    Metric("decision_match", _decision_match),
    Metric("reason_code_match", _reason_code_match),
    Metric("clause_precision", _clause_precision),
    Metric("tool_call_accuracy", _tool_call_accuracy),
]