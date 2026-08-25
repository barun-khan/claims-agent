from datetime import date
from decimal import Decimal
from src.contracts.claim import (
    Policy, ClaimFacts, SubmissionEvidence, Decision, ReasonCode,
    compute_settlement, adjudicate,
)

P = dict(version="2024.02", effective_from=date(2024, 1, 1), expires_on=date(2024, 12, 31),
         per_claim_limit=Decimal("120000"), annual_limit=Decimal("400000"),
         coinsurance_rate=Decimal("0.80"), exclusions=["PRC-9001"])


def pol(**kw):
    base = dict(policy_id="POL-1", remaining_deductible=Decimal("0"), **P)
    return Policy(**{**base, **kw})


def facts(**kw):
    base = dict(claim_id="C1", policy_id="POL-1", procedure_code="PRC-1010",
                billed_amount=Decimal("10000"), service_date=date(2024, 6, 1),
                provider_id="PRV-1")
    return ClaimFacts(**{**base, **kw})


def test_straightforward_approval():
    s = compute_settlement(facts(), pol())
    assert s.decision == Decision.APPROVE
    assert s.payout == Decimal("8000.00")


def test_deductible_exactly_equal_denies():
    s = compute_settlement(facts(), pol(remaining_deductible=Decimal("10000")))
    assert s.reason == ReasonCode.BELOW_DEDUCTIBLE


def test_one_day_after_expiry():
    s = compute_settlement(facts(service_date=date(2025, 1, 1)), pol())
    assert s.reason == ReasonCode.OUTSIDE_POLICY_PERIOD


def test_per_claim_cap_applied():
    s = compute_settlement(facts(billed_amount=Decimal("500000")), pol())
    assert s.payout == Decimal("96000.00")      # 120000 * 0.80
    assert s.decision == Decision.ESCALATE      # over high-value threshold


def test_triage_beats_coverage():
    ev = SubmissionEvidence(documents_present=["itemised_bill"])
    assert adjudicate(ev, facts(), pol()).reason == ReasonCode.MISSING_DOCUMENT