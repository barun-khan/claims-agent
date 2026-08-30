from __future__ import annotations
import asyncio, random
from evals.trace import AgentTrace, ToolCall

DECISIONS = ["approve", "deny", "escalate"]
REASONS = ["within_coverage", "excluded_procedure", "missing_document"]


async def always_escalate(case: dict) -> AgentTrace:
    """The laziest possible agent. Establishes your floor.

    If your real agent barely beats this, the extra accuracy is not coming
    from reasoning -- it is coming from the class distribution.
    """
    await asyncio.sleep(0)
    return AgentTrace(
        case_id=case["id"],
        output={"decision": "escalate", "payout": "0",
                "reason": "missing_document", "clauses": ["OPS-2.3"],
                "rationale": "stub", "confidence": 0.0},
        calls=[],
    )


async def random_guess(case: dict) -> AgentTrace:
    """Second floor: what chance alone achieves on this dataset."""
    await asyncio.sleep(0)
    rng = random.Random(case["id"])
    return AgentTrace(
        case_id=case["id"],
        output={"decision": rng.choice(DECISIONS), "payout": "0",
                "reason": rng.choice(REASONS), "clauses": ["POL-3.2"],
                "rationale": "stub", "confidence": 0.5},
        calls=[],
    )


async def oracle(case: dict) -> AgentTrace:
    """Perfect agent. Proves the harness itself is not broken.

    If this does not score 1.0 across the board, the bug is in your metrics,
    not in any agent. Tool arguments are populated from the oracle facts so
    that tool_argument_accuracy is exercised rather than skipped.
    """
    await asyncio.sleep(0)
    exp = case["expected"]
    facts = (case.get("oracle") or {}).get("facts") or {}
    return AgentTrace(
        case_id=case["id"],
        output={"decision": exp["decision"], "payout": exp["payout"],
                "reason": exp["reason"], "clauses": exp["clauses"],
                "rationale": "oracle", "confidence": 1.0},
        calls=[
            ToolCall(
                name=n,
                arguments={
                    "policy_id": facts.get("policy_id"),
                    "procedure_code": facts.get("procedure_code"),
                    "billed_amount": facts.get("billed_amount"),
                    "service_date": facts.get("service_date"),
                },
            )
            for n in case.get("expected_tool_calls", [])
        ],
    )


async def foundry(case: dict) -> AgentTrace:
    """The real agent. Imported lazily so the stubs stay usable without
    Azure credentials."""
    from src.agents.adjudicator import run_case
    return await run_case(case)


STUBS = {
    "always_escalate": always_escalate,
    "random": random_guess,
    "oracle": oracle,
    "foundry": foundry,
}