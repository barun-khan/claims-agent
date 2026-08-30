# 0007 — The critic is code, not a model

## Context

The critic pattern -- an adversarial reviewer checking whether an agent's
rationale is grounded in what its tools returned -- is standard multi-agent
practice. This project built one, measured it, and replaced it with fifteen
lines of Python.

## What was tried

**Attempt 1: LLM critic, broad scope.** Given the decision and the tool
call record, asked to verify every factual claim in the rationale.

Adversarial bucket fell from 1.000 to 0.533. Seven correct decisions were
overridden into escalations. `clause_precision` stayed at 1.000 throughout
-- the rationales were grounded; the critic flagged them anyway.

The cause was scope. The critic never receives the submission, so any
rationale statement sourced from the documents looks unsupported. It flagged
the agent correctly reporting that it had ignored an injection attempt.

**Attempt 2: LLM critic, narrowed.** Prompt rewritten to check only clause
ids, payout and reason code, with explicit instruction not to flag narrative
claims.

0.533 to 0.667. Still 33 points below the adjudicator alone. Every flag was
still a narrative claim -- six out of six. One flagged the agent quoting the
project's own prompt rule ("the bill is authoritative for extraction") as
unsupported, because no tool returned it.

"Verify this against the record" is a stronger pull on a model than "but
ignore these particular things."

**Attempt 3: deterministic check.** Fifteen lines of Python comparing the
decision's clause ids, payout and reason code against the tool results
already held in the trace.

1.000 across all metrics, three runs, zero spread, zero added cost.

## Decision

The critic is code. `src/agents/critic.py` performs the check without a
model. `src/agents/prompts/critic.v1.md` is retained as a record of the
rejected design.

## Rationale

The three claims worth checking are exact comparisons against data already
in memory. That is not reasoning. Asking a language model to do exact string
comparison introduces false positives while costing 46% more per claim and
roughly doubling latency.

| Design | adversarial | cost/claim |
|---|---|---|
| adjudicator alone | 1.000 | $0.022 |
| LLM critic, broad | 0.533 | $0.032 |
| LLM critic, narrowed | 0.667 | $0.031 |
| code critic | 1.000 | $0.022 |

## Consequences

The critic currently catches nothing, because `clause_precision` was already
1.000 before it existed. It is retained as a guardrail: it costs nothing, and
it will fire if a future prompt or model change starts producing ungrounded
citations. That is a regression detector, not an accuracy improvement, and
it should be described as one.

## Lesson

Multi-agent patterns are not free and are not automatically better. The
question is not "would a critic help" but "what would it catch that nothing
else does, and does that justify doubling cost and latency." Here the answer
was measurable, and it was no.