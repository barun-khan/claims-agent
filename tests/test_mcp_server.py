from tools.policy_rules.server import compute_settlement_tool
import json

POLICIES = json.load(open("tools/policy_rules/policies.json"))
SAMPLE_ID = next(iter(POLICIES))


def test_unknown_policy_returns_structured_error():
    r = compute_settlement_tool("POL-000000", "PRC-1010", 5000.0, "2024-06-01")
    assert r["error"] == "policy_not_found"
    assert "guidance" in r


def test_bad_date_returns_structured_error():
    r = compute_settlement_tool(SAMPLE_ID, "PRC-1010", 5000.0, "14/06/2024")
    assert r["error"] == "invalid_arguments"


def test_excluded_procedure_denied():
    r = compute_settlement_tool(SAMPLE_ID, "PRC-9001", 5000.0, "2024-06-01")
    assert r["decision"] == "deny"
    assert r["reason"] == "excluded_procedure"


def test_returns_grounding_context():
    r = compute_settlement_tool(SAMPLE_ID, "PRC-1010", 5000.0, "2024-06-01")
    assert "policy_version" in r and "clauses" in r