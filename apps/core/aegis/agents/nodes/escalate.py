"""escalate node: code, not LLM. Reached when loop_count exceeds 3 or the
gate structurally denies every proposed action (see gate.py)."""

from __future__ import annotations

from typing import Any

from aegis import db
from aegis.agents.state import AgentState
from aegis.events import emit


async def escalate(state: AgentState) -> dict[str, Any]:
    incident_id = state["incident"]["id"]
    loop_count = state.get("loop_count", 0)
    reason = (
        "loop_count exceeded max 3"
        if loop_count > 3
        else "gate denied every proposed action (tier gating arrives in phase 3)"
    )

    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "UPDATE aegis.incidents SET status = 'escalated', autonomy = 'escalated' WHERE id = $1",
            incident_id,
        )
        await emit(
            conn,
            incident_id=incident_id,
            type="incident.escalated",
            actor="system:supervisor",
            payload={"reason": reason, "loops_exhausted": loop_count > 3},
        )
    return {}
