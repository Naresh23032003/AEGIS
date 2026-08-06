"""aegis.worker: detection loop, LangGraph agent runs, supervisor.

Phase 2 adds the agent runtime. Three concurrent loops share one process:
detection (phase 1, unchanged), a dispatcher that claims newly detected
incidents and starts a graph run for each, and the supervisor (heartbeat
watchdog). On startup, any incident left in `resolving` by a killed worker
is resumed from its last LangGraph checkpoint before the dispatcher starts
claiming new ones (plan/06-milestones.md, Phase 2 acceptance: "killing
core-worker mid-run and restarting resumes the run from checkpoint").
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from aegis import db
from aegis.agents.graph import build_graph, checkpoint_conn_string, resume_incident, run_incident
from aegis.agents.supervisor import run_supervisor_loop
from aegis.detection import run_detection_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
logger = logging.getLogger("aegis.worker")

DISPATCH_POLL_SECONDS = 2

_INCIDENT_COLUMNS = (
    "id, title, severity, status, source_rule, affected_services, "
    "started_at, resolved_at, mttr_seconds, autonomy, summary"
)
# Both queries below interpolate only the fixed column list above, never
# request input; ruff's SQL-injection heuristic can't see that, hence noqa.
_SELECT_RESOLVING = f"SELECT {_INCIDENT_COLUMNS} FROM aegis.incidents WHERE status = 'resolving'"  # noqa: S608
_CLAIM_OPEN = (
    f"UPDATE aegis.incidents SET status = 'resolving' WHERE status = 'open' "  # noqa: S608
    f"RETURNING {_INCIDENT_COLUMNS}"
)


def _row_to_incident(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "severity": row["severity"],
        "status": row["status"],
        "source_rule": row["source_rule"],
        "affected_services": list(row["affected_services"]),
        "started_at": row["started_at"],
        "resolved_at": row["resolved_at"],
        "mttr_seconds": row["mttr_seconds"],
        "autonomy": row["autonomy"],
        "summary": row["summary"],
    }


async def _detection_snapshot(incident_id: str) -> dict[str, Any]:
    async with db.connection() as conn:
        row = await conn.fetchrow(
            "SELECT payload FROM aegis.incident_events "
            "WHERE incident_id = $1 AND type = 'incident.detected' ORDER BY seq ASC LIMIT 1",
            incident_id,
        )
    if row is None:
        return {}
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    metrics: dict[str, Any] = payload.get("metrics", {})
    return metrics


class Runner:
    """Tracks in-flight graph run tasks so the worker can await them on
    shutdown instead of leaking asyncio tasks."""

    def __init__(self, graph: Any) -> None:
        self.graph = graph
        self.tasks: set[asyncio.Task[None]] = set()

    def spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def resume(self, incident_id: str) -> None:
        await resume_incident(self.graph, incident_id=incident_id)

    async def resume_orphaned_runs(self) -> None:
        async with db.connection() as conn:
            rows = await conn.fetch(_SELECT_RESOLVING)
        for row in rows:
            incident_id = row["id"]
            logger.warning("resuming orphaned run for incident %s", incident_id)
            self.spawn(self.resume(incident_id))

    async def run_dispatch_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self._dispatch_once()
            except Exception:
                logger.exception("dispatch pass failed, continuing")
            try:
                await asyncio.wait_for(stop.wait(), timeout=DISPATCH_POLL_SECONDS)
            except TimeoutError:
                pass

    async def _dispatch_once(self) -> None:
        async with db.connection() as conn, conn.transaction():
            rows = await conn.fetch(_CLAIM_OPEN)
        for row in rows:
            incident = _row_to_incident(row)
            snapshot = await _detection_snapshot(incident["id"])
            logger.info("starting agent run for incident %s", incident["id"])
            self.spawn(run_incident(self.graph, incident=incident, detection_snapshot=snapshot))


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    await db.init_schema()

    async with AsyncPostgresSaver.from_conn_string(checkpoint_conn_string()) as checkpointer:
        await checkpointer.setup()
        graph = build_graph(checkpointer)
        runner = Runner(graph)

        await runner.resume_orphaned_runs()

        logger.info("worker started, detection loop polling every 5s")
        try:
            await asyncio.gather(
                run_detection_loop(stop),
                runner.run_dispatch_loop(stop),
                run_supervisor_loop(runner.resume, stop),
            )
        finally:
            if runner.tasks:
                await asyncio.gather(*runner.tasks, return_exceptions=True)
            await db.close_pool()
    logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
