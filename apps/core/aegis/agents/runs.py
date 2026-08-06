"""agent_runs bookkeeping: one row per LLM node invocation.

plan/02-contracts.md, Database schema (agent_runs). CLAUDE.md, Python:
"Heartbeat every 10s from running agent nodes." heartbeat() is a
background ticker started at node entry and cancelled at node exit; the
supervisor (aegis.agents.supervisor) watches last_heartbeat to detect a
hung node.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from ulid import ULID

from aegis import db
from aegis.events import emit

logger = logging.getLogger("aegis.agents.runs")

HEARTBEAT_SECONDS = 10


async def start_run(*, incident_id: str, agent: str, model: str) -> str:
    run_id = f"run_{ULID()}"
    now = datetime.now(UTC)
    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "INSERT INTO aegis.agent_runs "
            "(id, incident_id, agent, status, model, checkpoint_id, started_at, last_heartbeat) "
            "VALUES ($1, $2, $3, 'running', $4, $5, $6, $6)",
            run_id,
            incident_id,
            agent,
            model,
            incident_id,
            now,
        )
        await emit(
            conn,
            incident_id=incident_id,
            type="agent.run.started",
            actor=f"agent:{agent}",
            payload={"agent": agent, "model": model, "checkpoint_id": incident_id},
        )
    return run_id


async def heartbeat_once(run_id: str) -> None:
    async with db.connection() as conn:
        await conn.execute(
            "UPDATE aegis.agent_runs SET last_heartbeat = $1 WHERE id = $2",
            datetime.now(UTC),
            run_id,
        )


async def _heartbeat_loop(run_id: str) -> None:
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            await heartbeat_once(run_id)
    except asyncio.CancelledError:
        pass


@asynccontextmanager
async def heartbeat(run_id: str) -> AsyncIterator[None]:
    task = asyncio.create_task(_heartbeat_loop(run_id))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def complete_run(
    *,
    run_id: str,
    incident_id: str,
    agent: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    duration_ms: int,
) -> None:
    now = datetime.now(UTC)
    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "UPDATE aegis.agent_runs SET status = 'completed', ended_at = $1, "
            "tokens_in = $2, tokens_out = $3, cost_usd = $4, last_heartbeat = $1 WHERE id = $5",
            now,
            tokens_in,
            tokens_out,
            cost_usd,
            run_id,
        )
        await emit(
            conn,
            incident_id=incident_id,
            type="agent.run.completed",
            actor=f"agent:{agent}",
            payload={
                "agent": agent,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "duration_ms": duration_ms,
            },
        )


async def fail_run(*, run_id: str, incident_id: str, agent: str, reason: str) -> None:
    now = datetime.now(UTC)
    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "UPDATE aegis.agent_runs SET status = 'failed', ended_at = $1, last_heartbeat = $1 "
            "WHERE id = $2",
            now,
            run_id,
        )
        await emit(
            conn,
            incident_id=incident_id,
            type="agent.run.failed",
            actor=f"agent:{agent}",
            payload={"agent": agent, "reason": reason},
        )


async def step(
    *,
    incident_id: str,
    agent: str,
    phase: str,
    thought_summary: str,
    tool: str | None = None,
    tool_args_redacted: dict[str, Any] | None = None,
) -> None:
    async with db.connection() as conn, conn.transaction():
        await emit(
            conn,
            incident_id=incident_id,
            type="agent.step",
            actor=f"agent:{agent}",
            payload={
                "phase": phase,
                "thought_summary": thought_summary[:400],
                "tool": tool,
                "tool_args_redacted": tool_args_redacted or {},
            },
        )


async def latest_running_run(incident_id: str) -> dict[str, Any] | None:
    async with db.connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM aegis.agent_runs WHERE incident_id = $1 AND status = 'running' "
            "ORDER BY started_at DESC LIMIT 1",
            incident_id,
        )
    return dict(row) if row else None
