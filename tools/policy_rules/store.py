from __future__ import annotations
import json
from decimal import Decimal
from pathlib import Path
from src.contracts.claim import Policy

_STORE_PATH = Path(__file__).parent / "policies.json"


class PolicyNotFound(Exception):
    """Raised when a policy id is unknown. Surfaced to the model as a tool
    error rather than a crash -- the model must be able to react to it."""


def _load() -> dict[str, dict]:
    if not _STORE_PATH.exists():
        return {}
    return json.loads(_STORE_PATH.read_text())


def get_policy(policy_id: str) -> Policy:
    raw = _load().get(policy_id)
    if raw is None:
        raise PolicyNotFound(f"no policy with id {policy_id}")
    return Policy(**{k: (Decimal(v) if k in _MONEY else v) for k, v in raw.items()})


_MONEY = {"per_claim_limit", "annual_limit", "annual_paid_to_date",
          "remaining_deductible", "coinsurance_rate"}