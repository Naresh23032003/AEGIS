"""Supervisor: code, not LLM. plan/03-agents-and-policy.md, Supervisor:
"Watches agent_runs.last_heartbeat. If a run misses 3 heartbeats or fails
schema validation twice: emit agent.quarantined, attempt one resume from
the last checkpoint; if that fails, emit incident.escalated. The
supervisor never calls an LLM."

A run "misses 3 heartbeats" at the 10s cadence (aegis.agents.runs), so the
threshold here is 30s. Resume is attempted at most once per incident per
process lifetime (`_resumed` below); a second stall on the same incident
escalates immediately rather than resuming again, matching "one resume
attempt" in the spec.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from aegis import db
from aegis.events import emit

logger = logging.getLogger("aegis.agents.supervisor")

HEARTBEAT_SECONDS = 10
MISSED_HEARTBEATS_BEFORE_QUARANTINE = 3
STALE_AFTER_SECONDS = HEARTBEAT_SECONDS * MISSED_HEARTBEATS_BEFORE_QUARANTINE
POLL_SECONDS = 10

ResumeFn = Callable[[str], Awaitable[None]]


class Supervisor:
    def __init__(self, resume: ResumeFn) -> None:
        self._resume = resume
        self._resumed_once: set[str] = set()

    async def watch_once(self, *, now: datetime | None = None) -> list[str]:
        """Returns the incident_ids acted on this pass, for tests."""
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(seconds=STALE_AFTER_SECONDS)
        acted: list[str] = []

        async with db.connection() as conn:
            stale = await conn.fetch(
                "SELECT id, incident_id, agent FROM aegis.agent_runs "
                "WHERE status = 'running' AND last_heartbeat < $1",
                cutoff,
            )

        for row in stale:
            incident_id, agent, run_id = row["incident_id"], row["agent"], row["id"]
            acted.append(incident_id)

            if incident_id in self._resumed_once:
                await self._escalate(incident_id, "resumed run stalled again")
                continue

            await self._quarantine(run_id=run_id, incident_id=incident_id, agent=agent)
            self._resumed_once.add(incident_id)
            try:
                await self._resume(incident_id)
            except Exception:
                logger.exception("resume of incident %s failed", incident_id)
                await self._escalate(incident_id, "resume attempt raised")

        return acted

    async def _quarantine(self, *, run_id: str, incident_id: str, agent: str) -> None:
        async with db.connection() as conn, conn.transaction():
            await conn.execute(
                "UPDATE aegis.agent_runs SET status = 'quarantined' WHERE id = $1", run_id
            )
            await emit(
                conn,
                incident_id=incident_id,
                type="agent.quarantined",
                actor="system:supervisor",
                payload={"agent": agent, "reason": "missed 3 heartbeats", "recovery": "resume"},
            )
        logger.warning("quarantined run %s (incident %s, agent %s)", run_id, incident_id, agent)

    async def _escalate(self, incident_id: str, reason: str) -> None:
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
                payload={"reason": reason, "loops_exhausted": False},
            )
        logger.warning("escalated incident %s: %s", incident_id, reason)


async def run_supervisor_loop(resume: ResumeFn, stop: asyncio.Event) -> None:
    supervisor = Supervisor(resume)
    while not stop.is_set():
        try:
            await supervisor.watch_once()
        except Exception:
            logger.exception("supervisor pass failed, continuing")
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
        except TimeoutError:
            pass
