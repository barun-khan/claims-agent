# Agentic Claims Adjudication

![eval](https://github.com/barun-khan/claims-agent/actions/workflows/eval.yml/badge.svg)
![docker](https://github.com/barun-khan/claims-agent/actions/workflows/docker.yml/badge.svg)

An enterprise-grade agentic AI system for insurance claim adjudication,
built on the Azure AI stack.

## Design principles

**Determinism boundary.** The LLM decides *which* policy and *which* facts
apply. All coverage arithmetic and triage gating run as plain Python in
`src/contracts/claim.py`, unit tested and exposed to the agent as tools. The
model never computes a payout.

**Evaluation first.** The eval harness was built before the agent. Labels in
the golden dataset are computed by the rules engine, not written by a model,
so they are correct by construction. The dataset is regenerated from its
specification in CI and asserted byte-identical.

**Asymmetric error costs.** A false approval moves money out of the door; a
false denial produces a complaint. They do not share a threshold.

## Results

Measured over 3 runs of 220 cases each (660 agent invocations), gpt-5-mini
via Azure AI Foundry.

| Metric | Mean | Spread |
|---|---|---|
| decision_match | 0.988 | 0.009 |
| reason_code_match | 0.982 | 0.018 |
| tool_call_accuracy | 0.988 | 0.009 |
| schema_validity | 1.000 | 0.000 |
| **false_approval_rate** | **0.000** | **0.000** |

Cost $0.021 per claim. Latency p50 13s, p95 22s.

### Against measured baselines

| Agent | decision_match | false_approval_rate |
|---|---|---|
| oracle | 1.000 | 0.000 |
| **adjudicator** | **0.988** | **0.000** |
| always_escalate | 0.390 | 0.000 |
| random | 0.341 | 0.088 |

The headline figure is **60 points above the do-nothing floor**, not "98%
accurate." A stub that escalates every claim scores 0.390 on this dataset
purely from its class distribution, and it also scores a perfect 0.000 on
false approvals while being entirely useless. That is why the metrics are
never collapsed into a single number.

The oracle stub exists to test the harness rather than any agent: if a
perfect agent does not score 1.000, the bug is in the metrics.

## Adversarial testing

15 hand-written injection cases across five attack families — fake
authority, impersonated system messages, tool suppression, prose-asserted
figures, and pressure. Each carries an explicit `attack_goal` and
`failure_signature` so a failure names which defence broke.

All 15 pass. Two of them initially failed because the *label* was wrong, not
the agent: both times the agent applied the project's own contradiction rule
more consistently than its author had. See `docs/adr/0006`.

## Architecture


## Architecture

```
Claim submission
      |
Adjudicator agent  (Azure AI Foundry, gpt-5-mini)
      |
      +-- check_submission_tool   triage: missing docs, duplicates, contradictions
      +-- compute_settlement_tool coverage arithmetic, deterministic
      |
Grounding check    (code, not a model -- see ADR 0007)
      |
Structured decision + rationale citing only tool-returned clauses
```

## Running it

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -r requirements.txt

docker compose up -d                              # tool server
python -m evals.generate.build_dataset --offline  # rebuild the dataset
pytest tests/ -q                                  # unit + harness tests

python -m evals.runner --agent oracle             # verify the harness
python -m evals.runner --agent foundry --repeats 3
```

Azure credentials come from `az login` via `DefaultAzureCredential`. No API
keys appear in the codebase. See `.env.example` for required settings.

## Known limitations

- Offline-rendered documents are templated and signpost their discrepancies.
  Scores on `contradictory_evidence` are inflated relative to real prose.
- Tool call arguments are captured and scored, but tool *results* are not yet
  checked against the rationale. An agent citing a clause no tool returned
  would still pass every metric.
- The tool server runs on MCP 1.x, pinned by an agent-framework constraint.

## Status

Phase 2 complete: rules engine, 220-case stratified dataset, scoring harness
with CI gates, containerised MCP tool server, and a working adjudicator
agent on Azure AI Foundry.

Design decisions are recorded in `docs/adr/`.