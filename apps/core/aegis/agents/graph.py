"""The LangGraph StateGraph: one durable run per incident.
plan/03-agents-and-policy.md, Agent graph:

    triage -> diagnose -> plan_remediation -> gate -> execute -> verify
    verify --pass--> resolve
    verify --fail--> rollback -> diagnose        (loop_count += 1)
    loop_count > 3 -> escalate

Checkpointed in Postgres (AsyncPostgresSaver, schema `checkpoints`) so a
killed core-worker can resume an in-flight run: pass input=None with the
same thread_id (= incident_id) and LangGraph continues from the last
persisted checkpoint (see resume_incident below).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from aegis import db
from aegis.agents import nodes
from aegis.agents.state import AgentState, initial_state, resolve_scenario_hint
from aegis.events import emit

logger = logging.getLogger("aegis.agents.graph")

RECURSION_LIMIT = 50


def checkpoint_conn_string() -> str:
    return os.environ.get("AEGIS_DATABASE_URL", db.database_url())


def gate_router(state: AgentState) -> str:
    return "execute" if state.get("proposed_actions") else "escalate"


def verify_router(state: AgentState) -> str:
    verification = state.get("verification") or {}
    return "resolve" if verification.get("passed") else "rollback"


def rollback_router(state: AgentState) -> str:
    return "escalate" if state.get("loop_count", 0) > 3 else "diagnose"


def build_graph(checkpointer: AsyncPostgresSaver) -> Any:
    builder = StateGraph(AgentState)
    builder.add_node("triage", nodes.triage)
    builder.add_node("diagnose", nodes.diagnose)
    builder.add_node("plan_remediation", nodes.plan_remediation)
    builder.add_node("gate", nodes.gate)
    builder.add_node("execute", nodes.execute)
    builder.add_node("verify", nodes.verify)
    builder.add_node("rollback", nodes.rollback)
    builder.add_node("escalate", nodes.escalate)
    builder.add_node("resolve", nodes.resolve)

    builder.add_edge(START, "triage")
    builder.add_edge("triage", "diagnose")
    builder.add_edge("diagnose", "plan_remediation")
    builder.add_edge("plan_remediation", "gate")
    builder.add_conditional_edges(
        "gate", gate_router, {"execute": "execute", "escalate": "escalate"}
    )
    builder.add_edge("execute", "verify")
    builder.add_conditional_edges(
        "verify", verify_router, {"resolve": "resolve", "rollback": "rollback"}
    )
    builder.add_conditional_edges(
        "rollback", rollback_router, {"diagnose": "diagnose", "escalate": "escalate"}
    )
    builder.add_edge("escalate", END)
    builder.add_edge("resolve", END)

    return builder.compile(checkpointer=checkpointer)


async def _mark_escalated_on_crash(incident_id: str, exc: Exception) -> None:
    logger.exception("agent run for incident %s crashed", incident_id)
    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "UPDATE aegis.incidents SET status = 'escalated', autonomy = 'escalated' "
            "WHERE id = $1 AND status NOT IN ('resolved', 'escalated')",
            incident_id,
        )
        await emit(
            conn,
            incident_id=incident_id,
            type="incident.escalated",
            actor="system:supervisor",
            payload={"reason": f"agent run crashed: {exc}", "loops_exhausted": False},
        )


def _graph_config(incident_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": incident_id}, "recursion_limit": RECURSION_LIMIT}


async def run_incident(
    graph: Any, *, incident: dict[str, Any], detection_snapshot: dict[str, Any]
) -> None:
    """Fresh start for a newly detected incident. Does not call
    llm.reset_fixture_counters(): that clears every incident's mock-fixture
    counters, not just this one's, which corrupts any other incident still
    in flight in the same process (found live, see llm.py's module
    docstring). Fixture counters are now keyed by incident_id, so a new
    incident's sequence starts at 1 on its own; nothing to reset here."""
    incident_id = incident["id"]
    if incident.get("started_at") and isinstance(incident["started_at"], datetime):
        incident = {**incident, "started_at": incident["started_at"].isoformat()}
    scenario_hint = await resolve_scenario_hint(
        source_rule=incident["source_rule"],
        affected_services=incident.get("affected_services") or [],
    )
    state = initial_state(
        incident=incident, detection_snapshot=detection_snapshot, scenario_hint=scenario_hint
    )
    try:
        # A gate node reaching interrupt() (a red-tier proposal awaiting
        # approval) makes ainvoke return normally with "__interrupt__" in
        # the result, not raise; the run is legitimately parked, and there
        # is nothing further to do here (see resume_parked_run below).
        await graph.ainvoke(state, config=_graph_config(incident_id))
    except Exception as exc:  # noqa: BLE001 - never leave an incident stuck mid-run
        await _mark_escalated_on_crash(incident_id, exc)


async def resume_incident(graph: Any, *, incident_id: str) -> None:
    """Continue a run left mid-flight by a killed worker process. Passing
    None as input tells LangGraph to resume from the thread's last
    completed checkpoint rather than start over. Not for resuming a red-tier
    approval interrupt (see resume_parked_run): a plain crash never leaves a
    thread paused at interrupt() (nothing is "waiting", the process just
    died mid-node), so this always re-runs the last incomplete node from
    scratch."""
    try:
        await graph.ainvoke(None, config=_graph_config(incident_id))
    except Exception as exc:  # noqa: BLE001 - never leave an incident stuck mid-run
        await _mark_escalated_on_crash(incident_id, exc)


async def resume_parked_run(graph: Any, *, incident_id: str) -> None:
    """Wake a run parked at gate's interrupt() for a red-tier approval
    (aegis.agents.nodes.gate). The resume value itself is a throwaway: the
    action's outcome (approved/rejected/timed out) is read back from the
    actions table, not from this payload, so POST /approvals (a different
    process, core-api) only ever needs to update the database; this call
    is what actually wakes the paused graph in core-worker (see
    aegis.worker's approval dispatch loop)."""
    try:
        await graph.ainvoke(Command(resume="continue"), config=_graph_config(incident_id))
    except Exception as exc:  # noqa: BLE001 - never leave an incident stuck mid-run
        await _mark_escalated_on_crash(incident_id, exc)
