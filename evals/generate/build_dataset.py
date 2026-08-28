from __future__ import annotations
import argparse, json, random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import yaml
from src.contracts.claim import ClaimFacts, Policy, SubmissionEvidence, adjudicate

COVERED = ["PRC-1010", "PRC-1042", "PRC-2201", "PRC-2280", "PRC-3115"]
EXCLUDED = ["PRC-9001", "PRC-9014", "PRC-9077"]
NAMES = {"PRC-1010": "arthroscopic knee repair", "PRC-1042": "laparoscopic appendectomy",
         "PRC-2201": "cardiac stress testing", "PRC-2280": "coronary angioplasty",
         "PRC-3115": "lumbar decompression", "PRC-9001": "elective cosmetic rhinoplasty",
         "PRC-9014": "experimental gene therapy", "PRC-9077": "non-clinical wellness retreat"}

BASE = dict(version="2024.02", effective_from=date(2024, 1, 1), expires_on=date(2024, 12, 31),
            per_claim_limit=Decimal("120000"), annual_limit=Decimal("400000"),
            coinsurance_rate=Decimal("0.80"), exclusions=EXCLUDED)


def pick(rng, v):
    return rng.choice(v) if isinstance(v, list) else v


def service_date(rng, mode):
    start, end = BASE["effective_from"], BASE["expires_on"]
    if mode == "inside_period":
        return start + timedelta(days=rng.randint(10, (end - start).days - 10))
    if mode == "before_effective":
        return start - timedelta(days=rng.randint(5, 200))
    if mode == "after_expiry":
        return end + timedelta(days=rng.randint(5, 120))
    if mode == "one_day_after_expiry":
        return end + timedelta(days=1)
    raise ValueError(mode)


def amounts(rng, knobs):
    cap = BASE["per_claim_limit"]
    m = pick(rng, knobs.get("billed_amount_vs_limit", "well_below"))
    billed = {"well_below": lambda: Decimal(rng.randrange(4000, 60000, 50)),
              "just_above": lambda: cap + Decimal(rng.randrange(50, 3000, 50)),
              "far_above": lambda: cap * Decimal(rng.randint(2, 5))}[m]()

    d = pick(rng, knobs.get("deductible", "met"))
    ded = {"met": lambda: Decimal("0"),
           "partial": lambda: (billed * Decimal("0.15")).quantize(Decimal("1")),
           "just_below": lambda: billed - Decimal(rng.randrange(10, 200, 10)),
           "exactly_equal": lambda: billed,
           "just_above": lambda: billed + Decimal(rng.randrange(10, 200, 10))}[d]()
    return billed, max(Decimal("0"), ded)


def sample(rng, bucket):
    knobs = bucket.get("facts", {})
    ev = SubmissionEvidence(documents_present=["itemised_bill", "clinical_note"])

    if pick(rng, knobs.get("documents", "complete")) == "unparseable":
        return None, None, SubmissionEvidence(documents_present=[], extraction_confidence=0.1)

    doc = pick(rng, knobs.get("documents", "complete"))
    if doc == "no_clinical_note":
        ev.documents_present = ["itemised_bill"]
    elif doc == "no_itemised_bill":
        ev.documents_present = ["clinical_note"]
    if knobs.get("duplicate_of_prior"):
        ev.prior_claim_ids_same_service = [f"CLM-{rng.randint(10000, 99999)}"]
    if knobs.get("amount_disagreement"):
        ev.amount_disagreement = True

    pool = EXCLUDED if pick(rng, knobs.get("procedure", "covered")) == "excluded" else COVERED
    billed, ded = amounts(rng, knobs)
    paid = {"none": Decimal("0"),
            "partial": BASE["annual_limit"] * Decimal("0.85"),
            "exhausted": BASE["annual_limit"]}[pick(rng, knobs.get("annual_consumed", "none"))]

    pid = f"POL-{rng.randint(100000, 999999)}"
    policy = Policy(policy_id=pid, remaining_deductible=ded, annual_paid_to_date=paid, **BASE)
    facts = ClaimFacts(
        claim_id=f"CLM-{rng.randint(100000, 999999)}", policy_id=pid,
        procedure_code=rng.choice(pool), billed_amount=billed,
        service_date=service_date(rng, pick(rng, knobs.get("service_date", "inside_period"))),
        provider_id=f"PRV-{rng.randint(1000, 9999)}")
    return facts, policy, ev


def render_offline(facts, ev):
    """Deterministic rendering: no credentials, reproducible, free."""
    if facts is None:
        return "[unreadable scan -- no extractable content]"
    name = NAMES.get(facts.procedure_code, "procedure")
    out = ["ITEMISED BILL", f"Claim reference: {facts.claim_id}",
           f"Policy: {facts.policy_id}    Provider: {facts.provider_id}",
           f"Date of service: {facts.service_date.isoformat()}", "",
           f"  {facts.procedure_code}  {name} ........ {facts.billed_amount}",
           f"  TOTAL DUE ........................ {facts.billed_amount}"]
    if "clinical_note" in ev.documents_present:
        out += ["", "CLINICAL NOTE",
                f"Patient underwent {name} on {facts.service_date.isoformat()}.",
                "Procedure completed without complication. Discharged same day."]
    if ev.amount_disagreement:
        out += ["", f"Note: attending physician records total as {facts.billed_amount * 2}."]
    if ev.prior_claim_ids_same_service:
        out += ["", "Resubmitting as requested by claims department."]
    return "\n".join(out)


def expected_tools(label: dict) -> list[str]:
    """Triage always runs first. A blocked submission stops there; anything
    else proceeds to settlement."""
    blocked = (label["decision"] == "escalate"
               and label["reason"] != "high_value_review")
    return (["check_submission_tool"] if blocked
            else ["check_submission_tool", "compute_settlement_tool"])


def load_adversarial(path: Path, rng) -> list[dict]:
    """Hand-written cases. Labels still come from the rules engine -- the
    injection is text, it does not change what the policy says."""
    if not path.exists():
        print(f"WARNING: {path} not found, skipping adversarial bucket")
        return []

    spec = yaml.safe_load(path.read_text())
    if not spec or not spec.get("cases"):
        print(f"WARNING: {path} is empty or has no 'cases' key")
        return []

    rows = []
    for case in spec["cases"]:
        f = case["facts"]
        pid = f"POL-{rng.randint(100000, 999999)}"
        policy = Policy(policy_id=pid,
                        remaining_deductible=Decimal(str(f.get("deductible", 0))),
                        annual_paid_to_date=Decimal("0"), **BASE)
        facts = ClaimFacts(claim_id=f"CLM-{rng.randint(100000, 999999)}", policy_id=pid,
                           procedure_code=f["procedure_code"],
                           billed_amount=Decimal(str(f["billed_amount"])),
                           service_date=date.fromisoformat(f["service_date"]),
                           provider_id=f"PRV-{rng.randint(1000, 9999)}")
        ev = SubmissionEvidence(documents_present=["itemised_bill", "clinical_note"])
        label = adjudicate(ev, facts, policy).label()

        rows.append({
            "id": case["id"], "bucket": "adversarial",
            "tags": ["adversarial", case["family"]],
            "input": {"document_text": case["document"], "policy_id": pid,
                      "submitted_documents": ev.documents_present},
            "oracle": {"facts": json.loads(facts.model_dump_json()),
                       "policy": json.loads(policy.model_dump_json())},
            "expected": label,
            "expected_tool_calls": expected_tools(label),
            "_prior_claims": ev.prior_claim_ids_same_service,
            "attack_goal": case["attack_goal"],
            "failure_signature": case["failure_signature"],
            "verified": True})     # hand-written means hand-verified
    return rows


def build(taxonomy: Path, out: Path, offline: bool):
    spec = yaml.safe_load(taxonomy.read_text())
    rng = random.Random(spec["seed"])
    rows = []

    for bucket in spec["buckets"]:
        if bucket.get("handwritten"):
            adv = load_adversarial(Path("evals/specs/adversarial_cases.yaml"), rng)
            rows.extend(adv)
            print(f"loaded {len(adv)} hand-written cases for '{bucket['name']}'")
            continue

        for i in range(bucket["count"]):
            facts, policy, ev = sample(rng, bucket)
            label = adjudicate(ev, facts, policy).label()      # <- ground truth
            text = render_offline(facts, ev)
            rows.append({
                "id": f"{bucket['name']}-{i:03d}",
                "bucket": bucket["name"], "tags": [bucket["name"]],
                "input": {"document_text": text,
                          "policy_id": facts.policy_id if facts else None,
                          "submitted_documents": ev.documents_present},
                "oracle": {"facts": json.loads(facts.model_dump_json()) if facts else None,
                           "policy": json.loads(policy.model_dump_json()) if policy else None},
                "expected": label,
                "expected_tool_calls": expected_tools(label),
                "_prior_claims": ev.prior_claim_ids_same_service,
                "verified": False})

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"wrote {len(rows)} cases -> {out}")

    # Fixtures the tools read. Generated here so the dataset and the tool
    # data can never drift apart.
    store = {r["oracle"]["policy"]["policy_id"]: r["oracle"]["policy"]
             for r in rows if r["oracle"]["policy"]}
    Path("tools/policy_rules/policies.json").write_text(json.dumps(store, indent=1))
    print(f"wrote {len(store)} policies -> tools/policy_rules/policies.json")

    prior = {}
    for r in rows:
        dupes = r.get("_prior_claims")
        if dupes and r["oracle"]["facts"]:
            f = r["oracle"]["facts"]
            prior[f"{f['policy_id']}|{f['service_date']}|{f['procedure_code']}"] = dupes
    Path("tools/policy_rules/prior_claims.json").write_text(json.dumps(prior, indent=1))
    print(f"wrote {len(prior)} prior-claim records -> tools/policy_rules/prior_claims.json")

    print("\nNothing verified yet. Run --review before use.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--taxonomy", type=Path, default=Path("evals/specs/taxonomy.yaml"))
    ap.add_argument("--out", type=Path, default=Path("evals/datasets/golden_v1.jsonl"))
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    build(args.taxonomy, args.out, args.offline)