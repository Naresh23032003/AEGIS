"""Postgres access for aegis-db (schema `aegis`).

Phase 1 needs `incidents` and `incident_events` only; the remaining tables
in plan/02-contracts.md (actions, approvals, agent_runs, approver_keys)
arrive with the phases that use them. LangGraph's AsyncPostgresSaver owns
the separate `checkpoints` schema and is not touched here.
"""

from __future__ import annotations

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
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)


@asynccontextmanager
async def connection() -> AsyncIterator[asyncpg.pool.PoolConnectionProxy]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
