"""gate node: code, not LLM. plan/03-agents-and-policy.md: "gate is not an
LLM node. It calls OPA, opens veto windows, or waits on approval." Phase 3
replaces phase 2's green-only stub with the real thing: OPA decides every
proposal, yellow opens a 30s veto window the worker itself times (not the
DB), and red parks the run on a genuine LangGraph interrupt until
POST /approvals resumes it (aegis.worker's approval dispatch loop) or the
15 minute unanswered timeout rejects it (same loop).

Idempotency note: LangGraph re-executes this whole function from the start
on every resume, interrupt or crash-restart alike (plan/phases/phase-3.md,
Gotchas). Every side effect below (the OPA call, the events, the status
writes) is therefore guarded by first reading the action's current status:
"proposed" means this pass is the first time gate has looked at this
action; anything else means a previous pass already decided its policy
outcome, and this pass should only pick up where that left off.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from langgraph.types import interrupt

from aegis import approvals, db, policy
from aegis.agents.state import AgentState
from aegis.events import emit, format_ts

logger = logging.getLogger("aegis.agents.nodes.gate")

VETO_WINDOW_SECONDS = 30
VETO_POLL_SECONDS = 1


async def _actions_executed_count(conn: Any, incident_id: str) -> int:
    return int(
        await conn.fetchval(
            "SELECT count(*) FROM aegis.actions WHERE incident_id = $1 AND status = 'executed'",
            incident_id,
        )
    )


async def _already_scaled(conn: Any, incident_id: str, service: str | None) -> bool:
    """OPA policy rule 5 needs to know if this service is already scaled up;
    derived from this incident's own action history (executed scale_service
    calls not yet rolled back), never trusted from the model's params."""
    if service is None:
        return False
    row = await conn.fetchrow(
        "SELECT "
        "  count(*) FILTER (WHERE status = 'executed') AS up, "
        "  count(*) FILTER (WHERE status = 'rolled_back') AS down "
        "FROM aegis.actions WHERE incident_id = $1 AND catalog_key = 'scale_service' "
        "AND params->>'service' = $2",
        incident_id,
        service,
    )
    return bool(row and row["up"] > row["down"])


async def _action_status(conn: Any, action_id: str) -> str | None:
    status: str | None = await conn.fetchval(
        "SELECT status FROM aegis.actions WHERE id = $1", action_id
    )
    return status


async def _wait_for_veto_or_timeout(incident_id: str, action_id: str) -> str:
    """Blocks this node (i.e. this worker's asyncio task, not the DB) until
    a veto lands or the window closes. Recomputes the deadline from the
    persisted action.veto_window_opened event rather than holding it only
    in memory, so a node re-execution (crash-restart replay) picks up the
    real remaining time instead of granting a fresh 30 seconds."""
    async with db.connection() as conn:
        status = await _action_status(conn, action_id)
    if status != "executing":
        return status or "denied"

    closes_at = await approvals.veto_closes_at(incident_id, action_id)
    if closes_at is None:
        closes_at = datetime.now(UTC) + timedelta(seconds=VETO_WINDOW_SECONDS)

    while True:
        async with db.connection() as conn:
            status = await _action_status(conn, action_id)
        if status == "vetoed":
            return "vetoed"
        remaining = (closes_at - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            break
        await asyncio.sleep(min(VETO_POLL_SECONDS, remaining))

    # One last read to close the (sub-second) window between the poll above
    # and this function returning: a veto that lands in that instant must
    # still win (plan/phases/phase-3.md, Gotchas: "first writer wins").
    async with db.connection() as conn:
        status = await _action_status(conn, action_id)
    return "vetoed" if status == "vetoed" else "executing"


async def _apply_policy(
    conn: Any, *, incident: dict[str, Any], loop_count: int, action: dict[str, Any]
) -> None:
    """First-pass-only work for one action: OPA, action.policy_checked, and
    the status/event side effects for whichever tier allowed. Only ever
    runs once per action (guarded by the caller checking status=='proposed'
    first), so it does not need to be idempotent itself."""
    incident_id = incident["id"]
    action_id = action["action_id"]
    opa_params = dict(action["params"])
    if action["catalog_key"] == "scale_service":
        opa_params["already_scaled"] = await _already_scaled(
            conn, incident_id, action["params"].get("service")
        )

    try:
        decision = await policy.evaluate(
            action={
                "catalog_key": action["catalog_key"],
                "params": opa_params,
                "tier": action["tier"],
                "confidence": action["confidence"],
            },
            incident={
                "severity": incident.get("severity") or "sev2",
                "loop_count": loop_count,
                "actions_executed": await _actions_executed_count(conn, incident_id),
            },
            context={"env": "demo"},
        )
    except policy.PolicyError as exc:
        # Fail closed: an unreachable policy engine denies, it never allows.
        decision = policy.Decision(allow=False, rule_id="opa_unreachable", reason=str(exc))

    await emit(
        conn,
        incident_id=incident_id,
        type="action.policy_checked",
        actor="system:supervisor",
        payload={
            "action_id": action_id,
            "decision": "allow" if decision.allow else "deny",
            "opa_rule_id": decision.rule_id,
        },
    )
    policy_result = json.dumps(
        {"allow": decision.allow, "rule_id": decision.rule_id, "reason": decision.reason}
    )

    if not decision.allow:
        await conn.execute(
            "UPDATE aegis.actions SET status = 'denied', policy_result = $1::jsonb WHERE id = $2",
            policy_result,
            action_id,
        )
        return

    await conn.execute(
        "UPDATE aegis.actions SET policy_result = $1::jsonb WHERE id = $2", policy_result, action_id
    )
    if action["tier"] == "green":
        await conn.execute("UPDATE aegis.actions SET status = 'executing' WHERE id = $1", action_id)
    elif action["tier"] == "yellow":
        closes_at = datetime.now(UTC) + timedelta(seconds=VETO_WINDOW_SECONDS)
        await conn.execute("UPDATE aegis.actions SET status = 'executing' WHERE id = $1", action_id)
        await emit(
            conn,
            incident_id=incident_id,
            type="action.veto_window_opened",
            actor="system:supervisor",
            payload={"action_id": action_id, "closes_at": format_ts(closes_at)},
        )
    else:  # red
        await conn.execute(
            "UPDATE aegis.actions SET status = 'awaiting_approval' WHERE id = $1", action_id
        )
        await conn.execute(
            "UPDATE aegis.incidents SET status = 'awaiting_approval' WHERE id = $1", incident_id
        )
        await emit(
            conn,
            incident_id=incident_id,
            type="action.approval_requested",
            actor="system:supervisor",
            payload={
                "action_id": action_id,
                "diff": {"catalog_key": action["catalog_key"], "params": action["params"]},
                "reasoning": action.get("reasoning", ""),
            },
        )


async def gate(state: AgentState) -> dict[str, Any]:
    incident = state["incident"]
    incident_id = incident["id"]
    loop_count = state.get("loop_count", 0)
    allowed: list[dict[str, Any]] = []
    escalate_reason: str | None = None

    for action in state.get("proposed_actions", []):
        action_id = action["action_id"]

        async with db.connection() as conn:
            status = await _action_status(conn, action_id)
        if status is None or status == "proposed":
            async with db.connection() as conn, conn.transaction():
                await _apply_policy(conn, incident=incident, loop_count=loop_count, action=action)
            async with db.connection() as conn:
                status = await _action_status(conn, action_id)

        if status == "denied":
            escalate_reason = escalate_reason or (
                f"OPA denied {action['catalog_key']} ({action_id})"
            )
            continue

        if action["tier"] == "green":
            if status == "executing":
                allowed.append(action)
            continue

        if action["tier"] == "yellow":
            outcome = await _wait_for_veto_or_timeout(incident_id, action_id)
            if outcome == "executing":
                allowed.append(action)
            else:
                escalate_reason = escalate_reason or (
                    f"{action['catalog_key']} ({action_id}) was vetoed"
                )
            continue

        # red: park on a real interrupt until POST /approvals (or the 15
        # minute unanswered timeout) resumes this thread. The value passed
        # in is informational only (surfaced to whatever eventually drives
        # a console for this); the resume value coming back is a throwaway
        # too (see aegis.agents.graph.resume_parked_run) because the actual
        # decision lives in the database, which core-api (a different
        # process) already updated before anything resumes this thread.
        interrupt({"action_id": action_id, "catalog_key": action["catalog_key"], "tier": "red"})
        async with db.connection() as conn:
            outcome = await _action_status(conn, action_id) or "rejected"
        if outcome in ("approved", "executing"):
            async with db.connection() as conn, conn.transaction():
                await conn.execute(
                    "UPDATE aegis.actions SET status = 'executing' WHERE id = $1", action_id
                )
            allowed.append(action)
        else:
            escalate_reason = escalate_reason or (
                f"{action['catalog_key']} ({action_id}) was {outcome}"
            )

    return {"proposed_actions": allowed, "escalate_reason": escalate_reason}
