"""The adjudicator agent.

Reads a claim submission, extracts facts, calls the settlement tool, and
returns a structured decision. The model never computes coverage or payout
amounts -- that is the tool's job, and the prompt says so explicitly.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from pydantic import ValidationError

from evals.trace import AgentTrace, ToolCall
from src.agents.tools import check_submission_tool, compute_settlement_tool
from src.contracts.claim import ClaimDecision

# Absolute path derived from this module's location, so it resolves no
# matter which directory the process was started from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

PROMPT_PATH = PROJECT_ROOT / "src/agents/prompts/adjudicator.v1.md"

RESPONSE_SCHEMA = """

## Output format

Return ONLY a JSON object, no prose and no markdown fences:

{
  "decision": "approve" | "deny" | "escalate",
  "payout": "<amount as a string, e.g. 12000.00>",
  "reason": "<reason code exactly as the tool returned it>",
  "clauses": ["<clause ids exactly as the tool returned them>"],
  "rationale": "<two or three sentences explaining the outcome>",
  "confidence": <number between 0 and 1>
}
"""


def _user_message(case: dict) -> str:
    """The policy id is supplied by the system, not extracted from the
    document. A claimant does not get to choose which policy they are
    adjudicated under."""
    docs = ", ".join(case["input"]["submitted_documents"]) or "none"
    return (
        f"Policy ID: {case['input']['policy_id']}\n"
        f"Documents submitted: {docs}\n\n"
        f"--- BEGIN SUBMISSION ---\n"
        f"{case['input']['document_text']}\n"
        f"--- END SUBMISSION ---"
    )


def _parse_output(text: str) -> dict | None:
    """Strip fences, parse, validate. A malformed response is a measured
    schema-validity failure, not an exception."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return ClaimDecision(**json.loads(cleaned)).model_dump(mode="json")
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None


def _safe_json(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {"_raw": str(value)}


def _extract_calls(response) -> list[ToolCall]:
    """Content is a single union type, so we discriminate on `type`.
    Function calls and their results arrive as separate messages linked by
    call_id.

    Arguments and results are captured, not just names: an attack that
    corrupts a tool argument while leaving the decision intact is invisible
    to every name-only metric.
    """
    calls: dict[str, ToolCall] = {}
    order: list[str] = []

    for msg in response.messages:
        for c in getattr(msg, "contents", []):
            ctype = getattr(c, "type", None)
            if ctype == "function_call":
                cid = c.call_id
                order.append(cid)
                calls[cid] = ToolCall(name=c.name, arguments=_safe_json(c.arguments))
            elif ctype == "function_result" and c.call_id in calls:
                calls[c.call_id].result = _safe_json(c.result)

    return [calls[cid] for cid in order]


async def run_case(case: dict) -> AgentTrace:
    from agent_framework.foundry import FoundryChatClient

    t0 = time.perf_counter()
    instructions = PROMPT_PATH.read_text() + RESPONSE_SCHEMA

    try:
        # AzureCliCredential rather than DefaultAzureCredential: the latter
        # probes for a managed identity that cannot exist on a laptop,
        # costing ~2s per call before falling through to the CLI token.
        async with AzureCliCredential() as cred:
            agent = FoundryChatClient(
                credential=cred,
                model=os.environ["FOUNDRY_MODEL"],
            ).as_agent(
                name="adjudicator",
                instructions=instructions,
                tools=[check_submission_tool, compute_settlement_tool],
            )
            response = await agent.run(_user_message(case))
    except Exception as exc:
        # One transient failure must not abort a 220-case run. The runner
        # scores an errored trace as zero and continues.
        return AgentTrace(
            case_id=case["id"],
            error=repr(exc),
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    usage = response.usage_details or {}
    return AgentTrace(
        case_id=case["id"],
        output=_parse_output(response.text),
        raw_output=response.text,
        calls=_extract_calls(response),
        tokens_in=usage.get("input_token_count", 0),
        tokens_out=usage.get("output_token_count", 0),
        latency_ms=(time.perf_counter() - t0) * 1000,
    )