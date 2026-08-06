"""gate node: code, not LLM. plan/03-agents-and-policy.md: "gate is not an
LLM node. It calls OPA, opens veto windows, or waits on approval." Phase 2
only wires the green-tier path (plan/phases/phase-2.md, Gotchas: "the gate
node ... in this phase only handles green tier plus a hardcoded allow log;
leave clear seams for OPA and interrupts, they land in phase 3, do not
build them early"). Any yellow/red proposal this phase is structurally
denied rather than executed, since neither the veto window nor the
approval interrupt exists yet; the plan's edge diagram has no explicit
"gate deny" path, so this phase routes a deny straight to escalate rather
than spending loop budget retrying a tier gate that cannot change until
phase 3 (choice noted in the phase report).
"""

from __future__ import annotations

from typing import Any

from aegis import db
from aegis.agents.state import AgentState
from aegis.events import emit

STUB_ALLOW_RULE_ID = "phase2-stub-allow-green"
STUB_DENY_RULE_ID = "phase2-stub-deny-nongreen"


async def gate(state: AgentState) -> dict[str, Any]:
    incident_id = state["incident"]["id"]
    allowed: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []

    async with db.connection() as conn:
        for action in state.get("proposed_actions", []):
            if action["tier"] == "green":
                decision, rule_id, status = "allow", STUB_ALLOW_RULE_ID, "executing"
            else:
                decision, rule_id, status = "deny", STUB_DENY_RULE_ID, "denied"

            async with conn.transaction():
                await conn.execute(
                    "UPDATE aegis.actions SET status = $1 WHERE id = $2",
                    status,
                    action["action_id"],
                )
                await emit(
                    conn,
                    incident_id=incident_id,
                    type="action.policy_checked",
                    actor="system:supervisor",
                    payload={
                        "action_id": action["action_id"],
                        "decision": decision,
                        "opa_rule_id": rule_id,
                    },
                )
            (allowed if decision == "allow" else denied).append(action)

    return {"proposed_actions": allowed}
