"""resolve node: code, not LLM. Reached when verify passes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aegis import db
from aegis.agents.state import AgentState
from aegis.events import emit


async def resolve(state: AgentState) -> dict[str, Any]:
    incident = state["incident"]
    incident_id = incident["id"]
    now = datetime.now(UTC)

    async with db.connection() as conn:
        started_at = await conn.fetchval(
            "SELECT started_at FROM aegis.incidents WHERE id = $1", incident_id
        )
    mttr_seconds = int((now - started_at).total_seconds())

    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "UPDATE aegis.incidents SET status = 'resolved', resolved_at = $1, "
            "mttr_seconds = $2, autonomy = 'auto' WHERE id = $3",
            now,
            mttr_seconds,
            incident_id,
        )
        await emit(
            conn,
            incident_id=incident_id,
            type="incident.resolved",
            actor="system:supervisor",
            payload={
                "mttr_seconds": mttr_seconds,
                "autonomy": "auto",
                "actions_taken": state.get("executed_actions", []),
            },
        )
    return {}
