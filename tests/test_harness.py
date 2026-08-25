"""Meta-tests: these verify the eval harness itself, not any agent.

If these fail, every accuracy number the project reports is untrustworthy.
"""
import asyncio, json
from pathlib import Path
import pytest
from evals.runner import load_cases, run_agent, score, check_gates
from evals.stubs import STUBS
import yaml

DATASET = Path("evals/datasets/golden_v1.jsonl")
TAXONOMY = Path("evals/specs/taxonomy.yaml")


def _run(agent_name: str):
    cases = load_cases(DATASET)
    results = asyncio.run(run_agent(STUBS[agent_name], cases, 20))
    return score(results)


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load(TAXONOMY.read_text())


def test_dataset_exists_and_is_complete():
    cases = load_cases(DATASET)
    assert len(cases) >= 205
    assert {c["bucket"] for c in cases} >= {"happy_path", "adversarial", "deductible_edge"}


def test_oracle_scores_perfectly(spec):
    """If a perfect agent does not score 1.0, the metrics are broken."""
    rep = _run("oracle")
    for name, value in rep["metrics"].items():
        assert value == 1.0, f"{name} was {value}, expected 1.0 -- metric bug"
    assert rep["false_approval_rate"] == 0.0
    assert check_gates(rep, spec) == []


def test_stubs_fail_the_gates(spec):
    """If a do-nothing agent passes, the gates are not gating anything."""
    for stub in ("always_escalate", "random"):
        rep = _run(stub)
        assert check_gates(rep, spec), f"{stub} passed the gates -- gates too loose"


def test_baseline_floor_is_stable():
    """The do-nothing floor is a published number. If the dataset shifts,
    this fails and the README needs updating."""
    rep = _run("always_escalate")
    assert 0.35 <= rep["metrics"]["decision_match"] <= 0.45, (
        f"floor moved to {rep['metrics']['decision_match']:.3f}; "
        "dataset composition changed, update README baselines")