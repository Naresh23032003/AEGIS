"""HTTP client for OPA. plan/03-agents-and-policy.md, OPA policy: "The
worker calls OPA over HTTP for every proposal and emits action.policy_checked
with the rule id either way." The decision document itself lives in
packages/policies/aegis.rego, package aegis.actions, entry `decision`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

OPA_URL = os.environ.get("OPA_URL", "http://opa:8181")
DECISION_PATH = "/v1/data/aegis/actions/decision"


@dataclass(frozen=True)
class Decision:
    allow: bool
    rule_id: str
    reason: str


class PolicyError(RuntimeError):
    """OPA unreachable or returned a malformed response. Fails closed:
    callers must treat this the same as an explicit deny."""


async def evaluate(
    *, action: dict[str, Any], incident: dict[str, Any], context: dict[str, Any]
) -> Decision:
    payload = {"input": {"action": action, "incident": incident, "context": context}}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{OPA_URL}{DECISION_PATH}", json=payload)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as exc:
        raise PolicyError(f"OPA request failed: {exc}") from exc
    result = body.get("result")
    if not isinstance(result, dict) or "allow" not in result or "rule_id" not in result:
        raise PolicyError(f"OPA returned an unexpected shape: {body!r}")
    return Decision(
        allow=bool(result["allow"]),
        rule_id=str(result["rule_id"]),
        reason=str(result.get("reason", "")),
    )
