"""Postgres access for aegis-db (schema `aegis`).

Phase 1 added `incidents` and `incident_events`. Phase 2 adds `actions` and
`agent_runs` (plan/02-contracts.md, Database schema); `approvals` and
`approver_keys` arrive in phase 3 with signed approvals. LangGraph's
AsyncPostgresSaver owns the separate `checkpoints` schema and is not
touched here; it runs its own `setup()` migration (see aegis/agents/graph.py).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS aegis;

CREATE TABLE IF NOT EXISTS aegis.incidents (
    id text PRIMARY KEY,
    title text NOT NULL,
    severity text,
    status text NOT NULL,
    source_rule text NOT NULL,
    affected_services text[] NOT NULL DEFAULT '{}',
    started_at timestamptz NOT NULL,
    resolved_at timestamptz,
    mttr_seconds integer,
    autonomy text,
    summary text
);

CREATE TABLE IF NOT EXISTS aegis.incident_events (
    seq bigserial PRIMARY KEY,
    incident_id text NOT NULL,
    event_id text NOT NULL UNIQUE,
    type text NOT NULL,
    actor text NOT NULL,
    payload jsonb NOT NULL,
    prev_hash text NOT NULL,
    hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS incident_events_incident_id_seq_idx
    ON aegis.incident_events (incident_id, seq);

CREATE TABLE IF NOT EXISTS aegis.actions (
    id text PRIMARY KEY,
    incident_id text NOT NULL,
    catalog_key text NOT NULL,
    params jsonb NOT NULL,
    tier text NOT NULL,
    status text NOT NULL,
    confidence real,
    policy_result jsonb,
    reasoning text,
    proposed_by text,
    executed_at timestamptz,
    result jsonb
);

CREATE INDEX IF NOT EXISTS actions_incident_id_idx ON aegis.actions (incident_id);

-- One row per LLM agent-node invocation (triage/diagnose/plan_remediation/
-- verify), not per incident: plan/03's supervisor watches the single
-- currently-running row for an incident, so each node call gets its own
-- row rather than one row shared across the whole graph run.
CREATE TABLE IF NOT EXISTS aegis.agent_runs (
    id text PRIMARY KEY,
    incident_id text NOT NULL,
    agent text NOT NULL,
    status text NOT NULL,
    model text,
    tokens_in integer NOT NULL DEFAULT 0,
    tokens_out integer NOT NULL DEFAULT 0,
    cost_usd numeric(10,5) NOT NULL DEFAULT 0,
    checkpoint_id text,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    last_heartbeat timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS agent_runs_incident_id_idx ON aegis.agent_runs (incident_id);
CREATE INDEX IF NOT EXISTS agent_runs_status_heartbeat_idx
    ON aegis.agent_runs (status, last_heartbeat);
"""

_pool: asyncpg.Pool | None = None


def database_url() -> str:
    url = os.environ.get("AEGIS_DATABASE_URL")
    if not url:
        raise RuntimeError("AEGIS_DATABASE_URL is not set")
    return url


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(database_url(), min_size=1, max_size=10)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def init_schema() -> None:
    """core-api, core-worker, and core-executor (phase 2 onward) all call
    this independently at startup against the same fresh database. `CREATE
    ... IF NOT EXISTS` is not atomic across concurrent sessions in
    Postgres: two processes can both pass the existence check before
    either commits, and the loser gets a UniqueViolationError instead of a
    silent no-op. A couple of retries is enough since each failed attempt
    rolls back cleanly (asyncpg runs a multi-statement execute() as one
    implicit transaction) and, by the next attempt, whichever process won
    has already committed and IF NOT EXISTS is a true no-op."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        for attempt in range(3):
            try:
                await conn.execute(SCHEMA_SQL)
                return
            except asyncpg.exceptions.UniqueViolationError:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.2 * (attempt + 1))


@asynccontextmanager
async def connection() -> AsyncIterator[asyncpg.pool.PoolConnectionProxy]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
