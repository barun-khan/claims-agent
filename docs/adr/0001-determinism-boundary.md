# 0001 — Determinism boundary

## Context
The agent must produce payout amounts and coverage decisions that are
auditable and reproducible.

## Decision
The LLM decides *which* policy and *which* facts apply. All coverage
arithmetic and all triage gating run as plain Python in
`src/contracts/claim.py`. Ground-truth labels for the eval set are produced
by running that same code, never by asking a model.

## Consequences
- Labels are as correct as the rules engine, which is unit tested.
- The rules engine can be exposed as an MCP tool unchanged.
- A wrong payout is a code bug with a stack trace, not a prompt problem.

## Known gaps
- `contradictory_evidence` bucket collapses to a single reason code; all
  contradictions currently escalate. Immaterial contradictions should not.
- Offline rendering is templated; real documents vary far more.