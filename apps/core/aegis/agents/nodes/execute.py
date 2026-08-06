"""execute node: code, not LLM. Calls core-executor for each gate-allowed
action. plan/03-agents-and-policy.md, Node specs: "execute | none | executor
RPC | per plan/04"."""

from __future__ import annotations

import json
from typing import Any

from aegis import db
from aegis.agents import executor_client
from aegis.agents.state import AgentState


async def execute(state: AgentState) -> dict[str, Any]:
    incident_id = state["incident"]["id"]
    executed = list(state.get("executed_actions", []))

    for action in state.get("proposed_actions", []):
        try:
            result = await executor_client.execute(
                action_id=action["action_id"],
                incident_id=incident_id,
                catalog_key=action["catalog_key"],
                params=action["params"],
            )
            status = result.get("status", "executed")
        except executor_client.ExecutorError as exc:
            status = "failed"
            result = {"error": str(exc)}

        async with db.connection() as conn:
            await conn.execute(
                "UPDATE aegis.actions SET status = $1, executed_at = now(), result = $2::jsonb "
                "WHERE id = $3",
                status,
                json.dumps(result),
                action["action_id"],
            )
        if status == "executed":
            executed.append(action["action_id"])

    return {"executed_actions": executed}
