from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field


class Decision(StrEnum):
    APPROVE = "approve"; DENY = "deny"; ESCALATE = "escalate"


class ReasonCode(StrEnum):
    WITHIN_COVERAGE = "within_coverage"
    OUTSIDE_POLICY_PERIOD = "outside_policy_period"
    EXCLUDED_PROCEDURE = "excluded_procedure"
    BELOW_DEDUCTIBLE = "below_deductible"
    EXCEEDS_ANNUAL_LIMIT = "exceeds_annual_limit"
    MISSING_DOCUMENT = "missing_document"
    DUPLICATE_SUBMISSION = "duplicate_submission"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"
    UNPARSEABLE_SUBMISSION = "unparseable_submission"
    HIGH_VALUE_REVIEW = "high_value_review"


class Policy(BaseModel):
    policy_id: str
    version: str
    effective_from: date
    expires_on: date
    per_claim_limit: Decimal
    annual_limit: Decimal
    annual_paid_to_date: Decimal = Decimal("0")
    remaining_deductible: Decimal
    coinsurance_rate: Decimal = Field(ge=0, le=1)
    exclusions: list[str] = Field(default_factory=list)


class ClaimFacts(BaseModel):
    claim_id: str
    policy_id: str
    procedure_code: str
    billed_amount: Decimal
    service_date: date
    provider_id: str


class SubmissionEvidence(BaseModel):
    documents_present: list[str] = Field(default_factory=list)
    prior_claim_ids_same_service: list[str] = Field(default_factory=list)
    amount_disagreement: bool = False
    extraction_confidence: float = 1.0


class Settlement(BaseModel):
    decision: Decision
    payout: Decimal
    reason: ReasonCode
    clauses: list[str]

    def label(self) -> dict:
        return {"decision": self.decision.value, "payout": str(self.payout),
                "reason": self.reason.value, "clauses": sorted(self.clauses)}


class ClaimDecision(BaseModel):
    """What the agent must return. Used as a structured-output schema."""
    decision: Literal["approve", "deny", "escalate"]
    payout: Decimal
    reason: str
    clauses: list[str] = Field(min_length=1)
    rationale: str = Field(max_length=1200)
    confidence: float = Field(ge=0, le=1)


REQUIRED_DOCUMENTS = ("itemised_bill", "clinical_note")
HIGH_VALUE_THRESHOLD = Decimal("50000")
MIN_EXTRACTION_CONFIDENCE = 0.70


def _money(v: Decimal) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def triage(ev: SubmissionEvidence, facts: ClaimFacts | None) -> Settlement | None:
    """Gate checks before any coverage reasoning. Order is a business rule."""
    def esc(reason, clause):
        return Settlement(decision=Decision.ESCALATE, payout=Decimal("0"),
                          reason=reason, clauses=[clause])

    if facts is None or ev.extraction_confidence < MIN_EXTRACTION_CONFIDENCE:
        return esc(ReasonCode.UNPARSEABLE_SUBMISSION, "OPS-1.1")
    if any(d not in ev.documents_present for d in REQUIRED_DOCUMENTS):
        return esc(ReasonCode.MISSING_DOCUMENT, "OPS-2.3")
    if ev.prior_claim_ids_same_service:
        return esc(ReasonCode.DUPLICATE_SUBMISSION, "OPS-5.1")
    if ev.amount_disagreement:
        return esc(ReasonCode.CONTRADICTORY_EVIDENCE, "OPS-4.2")
    return None


def compute_settlement(facts: ClaimFacts, policy: Policy) -> Settlement:
    """Pure coverage arithmetic. Same inputs always give the same output."""
    def deny(reason, clause):
        return Settlement(decision=Decision.DENY, payout=Decimal("0"),
                          reason=reason, clauses=[clause])

    if facts.policy_id != policy.policy_id:
        raise ValueError("policy mismatch")
    if not (policy.effective_from <= facts.service_date <= policy.expires_on):
        return deny(ReasonCode.OUTSIDE_POLICY_PERIOD, "POL-1.1")
    if facts.procedure_code in policy.exclusions:
        return deny(ReasonCode.EXCLUDED_PROCEDURE, "POL-4.7")

    headroom = policy.annual_limit - policy.annual_paid_to_date
    if headroom <= 0:
        return deny(ReasonCode.EXCEEDS_ANNUAL_LIMIT, "POL-2.5")

    eligible = min(facts.billed_amount, policy.per_claim_limit)
    after_deductible = max(Decimal("0"), eligible - policy.remaining_deductible)
    if after_deductible <= 0:
        return deny(ReasonCode.BELOW_DEDUCTIBLE, "POL-3.1")

    payout = _money(min(after_deductible * policy.coinsurance_rate, headroom))
    clauses = ["POL-3.2", "POL-3.4"]
    if facts.billed_amount > policy.per_claim_limit:
        clauses.append("POL-2.4")
    if policy.remaining_deductible > 0:
        clauses.append("POL-3.1")

    if payout >= HIGH_VALUE_THRESHOLD:   # blast-radius control, not coverage
        return Settlement(decision=Decision.ESCALATE, payout=payout,
                          reason=ReasonCode.HIGH_VALUE_REVIEW,
                          clauses=sorted(clauses + ["OPS-7.1"]))

    return Settlement(decision=Decision.APPROVE, payout=payout,
                      reason=ReasonCode.WITHIN_COVERAGE, clauses=sorted(clauses))


def adjudicate(ev, facts, policy) -> Settlement:
    gated = triage(ev, facts)
    if gated is not None:
        return gated
    return compute_settlement(facts, policy)