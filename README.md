# Agentic Claims Adjudication

An enterprise-grade agentic AI system for insurance claim adjudication,
built on the Azure AI stack.

## Design principles

**Determinism boundary.** The LLM decides *which* policy and *which* facts
apply. All coverage arithmetic runs as plain Python in
`src/contracts/claim.py`, unit tested and exposed as an MCP tool.

**Evaluation first.** The eval harness was built before the agent. Labels in
the golden dataset are computed by the rules engine, not written by a model,
so they are correct by construction.

**Asymmetric error costs.** A false approval moves money out of the door; a
false denial produces a complaint. They do not share a threshold.

## Baselines

| Agent | decision_match | false_approval_rate |
|---|---|---|
| oracle | 1.000 | 0.000 |
| always_escalate | 0.390 | 0.000 |
| random | 0.341 | 0.088 |

`always_escalate` scoring 0.390 with perfect safety is why metrics are never
collapsed into a single score.

## Status

Phase 1: rules engine, stratified eval dataset, scoring harness with CI gates.
