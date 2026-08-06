"""Shared timing lookups for the yellow veto window and red approval flow,
derived from the event log rather than a dedicated DB column (plan/phases/
phase-3.md, Gotchas: "closes_at goes in the event so the UI can render the
countdown from data"). Deliberately outside aegis.agents so it can be
imported by aegis.api without pulling in the agent graph, LangGraph, or the
LLM client: core-api only ever reads these timestamps, it never runs a node.
"""

from __future__ import annotations

import json
from datetime import datetime

from aegis import db


async def veto_closes_at(incident_id: str, action_id: str) -> datetime | None:
    async with db.connection() as conn:
        row = await conn.fetchrow(
            "SELECT payload FROM aegis.incident_events "
            "WHERE incident_id = $1 AND type = 'action.veto_window_opened' "
            "AND payload->>'action_id' = $2 ORDER BY seq ASC LIMIT 1",
            incident_id,
            action_id,
        )
    if row is None:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    closes_at_str = payload.get("closes_at")
    if not closes_at_str:
        return None
    return datetime.fromisoformat(closes_at_str.replace("Z", "+00:00"))


async def approval_requested_at(incident_id: str, action_id: str) -> datetime | None:
    async with db.connection() as conn:
        requested_at: datetime | None = await conn.fetchval(
            "SELECT created_at FROM aegis.incident_events "
            "WHERE incident_id = $1 AND type = 'action.approval_requested' "
            "AND payload->>'action_id' = $2 ORDER BY seq ASC LIMIT 1",
            incident_id,
            action_id,
        )
    return requested_at
