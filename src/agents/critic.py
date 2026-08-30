"""The critic.

Checks whether the adjudicator's rationale is grounded in what the tools
actually returned. It does not re-adjudicate -- a second opinion on the
merits would give you two views and no tiebreaker.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

from evals.trace import AgentTrace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
PROMPT_PATH = PROJECT_ROOT / "src/agents/prompts/critic.v1.md"


def _review_message(trace: AgentTrace) -> str:
    calls = [
        {"tool": c.name, "arguments": c.arguments, "returned": c.result}
        for c in trace.calls
    ]
    return (
        f"DECISION UNDER REVIEW\n{json.dumps(trace.output, indent=2)}\n\n"
        f"TOOL CALL RECORD\n{json.dumps(calls, indent=2)}"
    )


def review(trace: AgentTrace) -> dict:
    """Grounding check. No model involved.

    An LLM critic was tried first and rejected: given the tool record and
    asked to verify the decision against it, it flagged narrative statements
    in the rationale six times out of six, including the agent correctly
    reporting that it had ignored an injection. Adversarial bucket fell from
    1.000 to 0.667 at 46% higher cost.

    The three claims worth checking are exact comparisons against a record
    already in memory. That is code, not reasoning.
    """
    if trace.output is None:
        return {"grounded": None, "note": "no parsable decision"}

    returned_clauses, returned_reasons, returned_payouts = set(), set(), set()
    for call in trace.calls:
        r = call.result or {}
        returned_clauses.update(r.get("clauses") or [])
        if r.get("reason"):
            returned_reasons.add(r["reason"])
        if r.get("payout") is not None:
            returned_payouts.add(_num(r["payout"]))

    unsupported = []
    invented = set(trace.output.get("clauses") or []) - returned_clauses
    if invented:
        unsupported.append(f"clauses not returned by any tool: {sorted(invented)}")

    if trace.output.get("reason") not in returned_reasons:
        unsupported.append(
            f"reason {trace.output.get('reason')!r} not returned by any tool")

    payout = _num(trace.output.get("payout"))
    if returned_payouts and payout not in returned_payouts:
        unsupported.append(
            f"payout {payout} does not match any tool result {sorted(returned_payouts)}")

    return {"grounded": not unsupported, "unsupported_claims": unsupported,
            "note": "" if not unsupported else "decision contains ungrounded values"}


def _num(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None