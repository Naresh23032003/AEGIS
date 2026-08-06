"""Seeds a synthetic incident with one red-tier action already proposed,
then runs a single-node graph (just gate) so it genuinely parks at
LangGraph's interrupt(), exactly as a real red-tier proposal would. Prints
one JSON line: {"incident_id": ..., "action_id": ...}.

Used by e2e/test_approvals.py to exercise the full signed-approval flow
(plan/06-milestones.md, Phase 3 acceptance: "a red-tier action visibly
parks until an approval signed by a registered key arrives") without
depending on the live LLM choosing to propose a red action, which none of
the five chaos scenarios' expected fix paths do on their own (the two red
catalog_keys, flush_queue and restart_database, are not any scenario's
answer).

Run inside core-worker (the one process with both the compiled graph's
modules and the checkpoints schema):
    docker compose exec -T core-worker python - < scripts/seed_red_action.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from aegis import db
from aegis.agents import nodes
from aegis.agents.graph import checkpoint_conn_string
from aegis.agents.state import AgentState, initial_state
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from ulid import ULID


async def main() -> None:
    incident_id = f"inc_{ULID()}"
    action_id = f"act_{ULID()}"
    now = datetime.now(UTC)

    await db.init_schema()
    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "INSERT INTO aegis.incidents "
            "(id, title, severity, status, source_rule, affected_services, started_at) "
            "VALUES ($1, $2, $3, 'resolving', $4, $5, $6)",
            incident_id,
            "synthetic red-tier test incident",
            "sev1",
            "synthetic",
            [],
            now,
        )
        await conn.execute(
            "INSERT INTO aegis.actions "
            "(id, incident_id, catalog_key, params, tier, status, confidence, reasoning, "
            "proposed_by) "
            "VALUES ($1, $2, 'restart_database', '{}'::jsonb, 'red', 'proposed', 0.95, "
            "'synthetic e2e test action', 'test:seed')",
            action_id,
            incident_id,
        )

    incident = {
        "id": incident_id,
        "title": "synthetic red-tier test incident",
        "severity": "sev1",
        "status": "resolving",
        "source_rule": "synthetic",
        "affected_services": [],
        "started_at": now.isoformat(),
    }
    action = {
        "action_id": action_id,
        "catalog_key": "restart_database",
        "params": {},
        "tier": "red",
        "confidence": 0.95,
        "reasoning": "synthetic e2e test action",
        "rollback_key": None,
    }
    state: AgentState = initial_state(incident=incident, detection_snapshot={})
    state["proposed_actions"] = [action]
    state["scenario"] = "red_tier_test"

    builder = StateGraph(AgentState)
    builder.add_node("gate", nodes.gate)
    builder.add_edge(START, "gate")
    builder.add_edge("gate", END)

    async with AsyncPostgresSaver.from_conn_string(checkpoint_conn_string()) as checkpointer:
        await checkpointer.setup()
        graph = builder.compile(checkpointer=checkpointer)
        result = await graph.ainvoke(
            state, config={"configurable": {"thread_id": incident_id}, "recursion_limit": 10}
        )
    if "__interrupt__" not in result:
        raise RuntimeError(f"gate did not park on the red action: {result}")

    print(json.dumps({"incident_id": incident_id, "action_id": action_id}))
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
