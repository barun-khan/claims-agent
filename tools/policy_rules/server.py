"""MCP server exposing the deterministic settlement calculator.

This server contains no AI. It is the boundary that keeps coverage
arithmetic out of the language model's hands.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation

from mcp.server.fastmcp import FastMCP

from src.contracts.claim import ClaimFacts, compute_settlement
from tools.policy_rules.store import PolicyNotFound, get_policy

mcp = FastMCP("policy-rules")


@mcp.tool()
def compute_settlement_tool(
    policy_id: str,
    procedure_code: str,
    billed_amount: float,
    service_date: str,
) -> dict:
    """Compute the exact settlement for a claim under a policy.

    Returns the coverage decision, the payout amount, a machine-readable
    reason code, and the policy clauses that were applied.

    Use this for ALL coverage and payout calculations. Never compute
    deductibles, coinsurance, caps, or payout amounts yourself -- your
    arithmetic is not auditable and will not match the policy engine.

    Args:
        policy_id: Policy identifier, e.g. "POL-482913".
        procedure_code: Procedure code from the itemised bill, e.g. "PRC-1010".
        billed_amount: Total amount billed, as a number, e.g. 12500.00.
        service_date: Date of service in ISO format, e.g. "2024-06-14".
    """
    try:
        policy = get_policy(policy_id)
    except PolicyNotFound as exc:
        return {"error": "policy_not_found", "detail": str(exc),
                "guidance": "Escalate to a human adjuster. Do not guess."}

    try:
        facts = ClaimFacts(
            claim_id="tool-call", policy_id=policy_id, provider_id="unknown",
            procedure_code=procedure_code,
            billed_amount=Decimal(str(billed_amount)),
            service_date=date.fromisoformat(service_date),
        )
    except (ValueError, InvalidOperation) as exc:
        return {"error": "invalid_arguments", "detail": str(exc),
                "guidance": "Re-read the documents and call again with corrected values."}

    s = compute_settlement(facts, policy)
    return {
        "decision": s.decision.value,
        "payout": str(s.payout),
        "reason": s.reason.value,
        "clauses": s.clauses,
        "policy_version": policy.version,
        "policy_period": f"{policy.effective_from} to {policy.expires_on}",
    }

@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Liveness probe. Deliberately does no work beyond confirming the
    process is serving. A probe that checks dependencies turns a downstream
    outage into a restart loop."""
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok", "service": "policy-rules"})

if __name__ == "__main__":
    import os
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        import uvicorn
        uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=8080)
    else:
        mcp.run()