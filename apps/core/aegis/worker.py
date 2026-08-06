"""aegis.worker: detection loop, LangGraph agent runs, supervisor.

Phase 2 adds the agent runtime. Phase 3 adds a fourth loop: approval
dispatch, which wakes a red-tier run parked at gate's interrupt() once
POST /approvals (a different process, core-api) has recorded a decision in
the database, and times out any action still awaiting_approval after 15
minutes unanswered (plan/03-agents-and-policy.md, Risk tiers). core-api
cannot resume the graph itself, since the compiled graph object only lives
in this process; it only ever writes the outcome, this loop is what wakes
the paused thread.

Four concurrent loops share one process: detection (phase 1, unchanged), a
dispatcher that claims newly detected incidents and starts a graph run for
each, the supervisor (heartbeat watchdog), and approval dispatch. On
startup, any incident left in `resolving` by a killed worker is resumed
from its last LangGraph checkpoint before the dispatcher starts claiming
new ones (plan/06-milestones.md, Phase 2 acceptance: "killing core-worker
mid-run and restarting resumes the run from checkpoint"). An incident
parked in `awaiting_approval` is not touched by that startup sweep: it is
not orphaned, it is legitimately waiting on a human, and only the approval
loop below ever wakes it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from datetime import UTC, datetime, timedelta
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from aegis import approvals, db
from aegis.agents.graph import (
    build_graph,
    checkpoint_conn_string,
    resume_incident,
    resume_parked_run,
    run_incident,
)
from aegis.agents.supervisor import run_supervisor_loop
from aegis.detection import run_detection_loop
from aegis.events import emit

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
logger = logging.getLogger("aegis.worker")

DISPATCH_POLL_SECONDS = 2
APPROVAL_POLL_SECONDS = 5
APPROVAL_TIMEOUT_SECONDS = 15 * 60

_CLAIM_RESOLVED_APPROVALS = """
UPDATE aegis.incidents SET status = 'resolving'
WHERE status = 'awaiting_approval' AND id IN (
    SELECT incident_id FROM aegis.actions WHERE status IN ('approved', 'rejected')
)
RETURNING id
"""  # noqa: S608 - no interpolated input, fixed query

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
    shutdown instead of leaking asyncio tasks, and so at most one graph
    invocation ever runs per incident_id at a time.

    The second guarantee matters live in a way phase 2's two scenarios
    never exercised: a diagnose call stuck behind Groq 429 backoff can run
    well past the supervisor's 30s stale-heartbeat threshold while still
    being perfectly alive, not hung. The supervisor would otherwise
    "resume" it anyway, and since resume_incident starts a second, fully
    independent graph.ainvoke against the same thread_id, both the
    original task and the resume would run to completion concurrently,
    each executing its own remediation and emitting its own
    incident.resolved. in_flight is the guard against that: the
    supervisor's resume is a no-op for an incident that is (still) here.
    """

    def __init__(self, graph: Any) -> None:
        self.graph = graph
        self.tasks: set[asyncio.Task[None]] = set()
        self.in_flight: set[str] = set()

    def spawn(self, incident_id: str, coro: Any) -> None:
        if incident_id in self.in_flight:
            logger.warning(
                "skipping graph run for incident %s: one is already in flight", incident_id
            )
            return
        self.in_flight.add(incident_id)
        task = asyncio.create_task(coro)
        self.tasks.add(task)

        def _done(t: asyncio.Task[None]) -> None:
            self.tasks.discard(t)
            self.in_flight.discard(incident_id)

        task.add_done_callback(_done)

    async def resume(self, incident_id: str) -> None:
        if incident_id in self.in_flight:
            logger.warning(
                "supervisor asked to resume incident %s but it is still running "
                "(likely a slow LLM call, not a real stall); skipping",
                incident_id,
            )
            return
        await resume_incident(self.graph, incident_id=incident_id)

    async def resume_parked(self, incident_id: str) -> None:
        await resume_parked_run(self.graph, incident_id=incident_id)

    async def resume_orphaned_runs(self) -> None:
        async with db.connection() as conn:
            rows = await conn.fetch(_SELECT_RESOLVING)
        for row in rows:
            incident_id = row["id"]
            logger.warning("resuming orphaned run for incident %s", incident_id)
            self.spawn(incident_id, self.resume(incident_id))

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
            self.spawn(
                incident["id"],
                run_incident(self.graph, incident=incident, detection_snapshot=snapshot),
            )

    async def run_approval_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self._time_out_stale_approvals()
                await self._dispatch_resolved_approvals()
            except Exception:
                logger.exception("approval dispatch pass failed, continuing")
            try:
                await asyncio.wait_for(stop.wait(), timeout=APPROVAL_POLL_SECONDS)
            except TimeoutError:
                pass

    async def _time_out_stale_approvals(self) -> None:
        """plan/03-agents-and-policy.md, Risk tiers: red "escalates to
        incident.escalated after 15 minutes unanswered." Times out by
        rejecting the action (system:supervisor, not a forged human
        signature) so the paused gate node's own approve/reject handling
        picks it up uniformly; the incident reaches incident.escalated via
        the normal gate -> escalate path once the run resumes, not directly
        from here."""
        async with db.connection() as conn:
            stale = await conn.fetch(
                "SELECT id, incident_id FROM aegis.actions WHERE status = 'awaiting_approval'"
            )
        cutoff = datetime.now(UTC) - timedelta(seconds=APPROVAL_TIMEOUT_SECONDS)
        for row in stale:
            requested_at = await approvals.approval_requested_at(row["incident_id"], row["id"])
            if requested_at is None or requested_at > cutoff:
                continue
            async with db.connection() as conn, conn.transaction():
                updated = await conn.fetchrow(
                    "UPDATE aegis.actions SET status = 'rejected' "
                    "WHERE id = $1 AND status = 'awaiting_approval' RETURNING id",
                    row["id"],
                )
                if updated is not None:
                    await emit(
                        conn,
                        incident_id=row["incident_id"],
                        type="action.rejected",
                        actor="system:supervisor",
                        payload={
                            "action_id": row["id"],
                            "approver_pubkey": "",
                            "signature": "",
                            "reason": "15 minute approval window expired unanswered",
                        },
                    )
            if updated is not None:
                logger.warning("action %s timed out awaiting approval", row["id"])

    async def _dispatch_resolved_approvals(self) -> None:
        async with db.connection() as conn, conn.transaction():
            rows = await conn.fetch(_CLAIM_RESOLVED_APPROVALS)
        for row in rows:
            logger.info("resuming incident %s after approval decision", row["id"])
            self.spawn(row["id"], self.resume_parked(row["id"]))


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
                runner.run_approval_loop(stop),
                run_supervisor_loop(runner.resume, stop),
            )
        finally:
            if runner.tasks:
                await asyncio.gather(*runner.tasks, return_exceptions=True)
            await db.close_pool()
    logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
