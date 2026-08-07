"""Seeds a synthetic incident with one yellow-tier action already proposed,
then runs a gate -> (execute | escalate) graph so a real 30 second veto
window opens on it. Prints one JSON line, {"incident_id": ..., "action_id":
...}, and flushes it before the graph starts, so the caller has the
action_id while the window is still open.

The sibling of scripts/seed_red_action.py, and for the same reason. That
one exists because no chaos scenario's expected fix path is a red action,
so nothing would ever naturally propose one. This one exists because the
yellow action a scenario does normally produce comes from a live model, and
in the phase 8 live run it did not: diagnose returned confidence 0.0 on the
error_spike incident, plan_remediation proposed a green remove_toxic for an
error-rate fault, OPA denied it on deny_low_confidence, and no veto window
ever opened (docs/reports/FINAL_VERIFICATION.md, The four failures). Policy
was right. The test was the thing that broke, because it was testing the
veto window through a model's choice of action.

Seeding rollback_config on target-payments, which is exactly what
plan/03's chaos table expects error_spike to produce, keeps the action's
identity while removing the model from the path.

The graph keeps the real gate_router: a veto that fails to land routes to
execute, and the test's "nothing executed" assertion then fails as it
should. Run inside core-worker:
    docker compose exec -T core-worker python - < scripts/seed_yellow_action.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime

from aegis import db
from aegis.agents import nodes
from aegis.agents.graph import checkpoint_conn_string, gate_router
from aegis.agents.state import AgentState, initial_state
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from ulid import ULID

CATALOG_KEY = "rollback_config"
PARAMS = {"service": "target-payments"}


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
            "synthetic yellow-tier test incident",
            "sev2",
            "synthetic",
            ["target-payments"],
            now,
        )
        await conn.execute(
            "INSERT INTO aegis.actions "
            "(id, incident_id, catalog_key, params, tier, status, confidence, reasoning, "
            "proposed_by) "
            "VALUES ($1, $2, $3, $4::jsonb, 'yellow', 'proposed', 0.9, "
            "'synthetic e2e test action', 'test:seed')",
            action_id,
            incident_id,
            CATALOG_KEY,
            json.dumps(PARAMS),
        )

    incident = {
        "id": incident_id,
        "title": "synthetic yellow-tier test incident",
        "severity": "sev2",
        "status": "resolving",
        "source_rule": "synthetic",
        "affected_services": ["target-payments"],
        "started_at": now.isoformat(),
    }
    action = {
        "action_id": action_id,
        "catalog_key": CATALOG_KEY,
        "params": PARAMS,
        "tier": "yellow",
        "confidence": 0.9,
        "reasoning": "synthetic e2e test action",
        "rollback_key": CATALOG_KEY,
    }
    state: AgentState = initial_state(incident=incident, detection_snapshot={})
    state["proposed_actions"] = [action]
    state["scenario"] = "yellow_tier_test"

    # The caller needs this before gate's 30 second window closes, and the
    # ainvoke below blocks for the whole of it.
    print(json.dumps({"incident_id": incident_id, "action_id": action_id}), flush=True)
    sys.stdout.flush()

    builder = StateGraph(AgentState)
    builder.add_node("gate", nodes.gate)
    builder.add_node("execute", nodes.execute)
    builder.add_node("escalate", nodes.escalate)
    builder.add_edge(START, "gate")
    builder.add_conditional_edges(
        "gate", gate_router, {"execute": "execute", "escalate": "escalate"}
    )
    builder.add_edge("execute", END)
    builder.add_edge("escalate", END)

    async with AsyncPostgresSaver.from_conn_string(checkpoint_conn_string()) as checkpointer:
        await checkpointer.setup()
        graph = builder.compile(checkpointer=checkpointer)
        await graph.ainvoke(
            state, config={"configurable": {"thread_id": incident_id}, "recursion_limit": 10}
        )
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
