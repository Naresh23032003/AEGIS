"""resolve node: code, not LLM. Reached when verify passes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aegis import db
from aegis.agents.state import AgentState
from aegis.events import emit


async def _autonomy(conn: Any, incident_id: str) -> str:
    """plan/02-contracts.md: autonomy is auto/approved/escalated. Yellow's
    veto window is a safety net the run clears on its own (still "auto"
    end to end); red genuinely needed a human's signed decision to get
    here, which is exactly what a row in aegis.approvals with decision
    'approve' records (aegis.api's POST /approvals)."""
    approved = await conn.fetchval(
        "SELECT 1 FROM aegis.approvals a JOIN aegis.actions act ON act.id = a.action_id "
        "WHERE act.incident_id = $1 AND a.decision = 'approve' LIMIT 1",
        incident_id,
    )
    return "approved" if approved else "auto"


async def resolve(state: AgentState) -> dict[str, Any]:
    incident = state["incident"]
    incident_id = incident["id"]
    now = datetime.now(UTC)

    async with db.connection() as conn:
        started_at = await conn.fetchval(
            "SELECT started_at FROM aegis.incidents WHERE id = $1", incident_id
        )
        autonomy = await _autonomy(conn, incident_id)
    mttr_seconds = int((now - started_at).total_seconds())

    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "UPDATE aegis.incidents SET status = 'resolved', resolved_at = $1, "
            "mttr_seconds = $2, autonomy = $3 WHERE id = $4",
            now,
            mttr_seconds,
            autonomy,
            incident_id,
        )
        await emit(
            conn,
            incident_id=incident_id,
            type="incident.resolved",
            actor="system:supervisor",
            payload={
                "mttr_seconds": mttr_seconds,
                "autonomy": autonomy,
                "actions_taken": state.get("executed_actions", []),
            },
        )
    return {}
