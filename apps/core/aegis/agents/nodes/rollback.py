"""rollback node: code, not LLM. plan/03-agents-and-policy.md edge diagram:
verify --fail--> rollback -> diagnose (loop_count += 1).

Every green-tier action in this phase's catalog has rollback_key: null
(plan/03, Action catalog: restart_service/clear_cache/remove_toxic all
need "none" or no rollback); yellow's scale_service and rollback_config
both point rollback_key at themselves. Phase 3 wires scale_service and
rollback_config for real (PHASE_2_REPORT.md flagged both as untested
stubs), so this node's rollback_key branch is now exercised."""

from __future__ import annotations

import logging
from typing import Any

from aegis import db
from aegis.agents import executor_client
from aegis.agents.state import AgentState
from aegis.events import emit

logger = logging.getLogger("aegis.agents.rollback")


def _rollback_params(action: dict[str, Any]) -> dict[str, Any]:
    """rollback_config's rollback (restart again with faults cleared) and
    remove_toxic (n/a, rollback_key is null) can reuse the original params
    unchanged. scale_service is the one case where "undo" is not "repeat":
    plan/03's catalog table rollback is "scale back to 1", not "scale to 2"
    again, so replicas is overridden here rather than trusting the
    proposal's own params (aegis.actions.catalog is params-blind to this
    distinction; it is a rollback-direction concern, not a catalog one)."""
    if action["rollback_key"] == "scale_service":
        return {**action["params"], "replicas": 1}
    params: dict[str, Any] = action["params"]
    return params


async def rollback(state: AgentState) -> dict[str, Any]:
    incident_id = state["incident"]["id"]
    executed_ids = set(state.get("executed_actions", []))

    for action in state.get("proposed_actions", []):
        if action["action_id"] not in executed_ids or not action.get("rollback_key"):
            continue
        try:
            await executor_client.execute(
                action_id=f"{action['action_id']}_rollback",
                incident_id=incident_id,
                catalog_key=action["rollback_key"],
                params=_rollback_params(action),
            )
        except executor_client.ExecutorError:
            logger.exception("rollback of %s failed", action["action_id"])
        async with db.connection() as conn, conn.transaction():
            await emit(
                conn,
                incident_id=incident_id,
                type="action.rolled_back",
                actor="system:supervisor",
                payload={"action_id": action["action_id"], "rollback_of": action["action_id"]},
            )

    return {"loop_count": state.get("loop_count", 0) + 1}
