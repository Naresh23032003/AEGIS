"""rollback node: code, not LLM. plan/03-agents-and-policy.md edge diagram:
verify --fail--> rollback -> diagnose (loop_count += 1).

Every green-tier action in this phase's catalog has rollback_key: null
(plan/03, Action catalog: restart_service/clear_cache/remove_toxic all
need "none" or no rollback), so this node is a no-op passthrough for both
scenarios phase 2 exercises live. The rollback_key branch below exists for
completeness and is untested this phase, noted in the phase report."""

from __future__ import annotations

import logging
from typing import Any

from aegis import db
from aegis.agents import executor_client
from aegis.agents.state import AgentState
from aegis.events import emit

logger = logging.getLogger("aegis.agents.rollback")


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
                params=action["params"],
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
