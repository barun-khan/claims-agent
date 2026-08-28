"""Tools exposed to the adjudicator agent.

The agent framework derives the tool schema from this function's signature
and docstring, so the docstring here is a prompt, not documentation. It is
the only instruction the model receives about this tool.
"""
from tools.policy_rules.server import compute_settlement_tool as _compute


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
    return _compute(policy_id, procedure_code, billed_amount, service_date)
