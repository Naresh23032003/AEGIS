"""Envelope construction and chained emission.

plan/02-contracts.md, Event envelope and Event catalog. plan/04-security.md,
Hash-chained audit log. Every event is built here so the Postgres chain
write and the Redis publish always happen together, in that order, inside
the caller's transaction.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import asyncpg
import redis.exceptions
from ulid import ULID

from aegis.chain import next_hash
from aegis.contracts import EventEnvelope
from aegis.redis_stream import STREAM_KEY, get_redis

logger = logging.getLogger("aegis.events")


def format_ts(dt: datetime) -> str:
    """Same string shape as build_envelope's ts, for re-serializing rows
    read back out of incident_events."""
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def build_envelope(
    *, incident_id: str, type: str, actor: str, payload: dict[str, Any], now: datetime
) -> dict[str, Any]:
    envelope = {
        "id": str(ULID()),
        "ts": format_ts(now),
        "type": type,
        "incident_id": incident_id,
        "actor": actor,
        "payload": payload,
    }
    EventEnvelope.model_validate(envelope)  # shape check before it ever reaches storage
    return envelope


def verify_row_chain(incident_id: str, rows: list[asyncpg.Record]) -> dict[str, Any]:
    """Recompute the hash chain from already-fetched incident_events rows.

    Shared by GET .../verify-chain (aegis.api) and the evidence pack (phase
    6, plan/phases/phase-6.md), which both need the identical check and, in
    the pack's case, already has the rows in hand from building the
    timeline: no reason to run the query twice.
    """
    prev_hash = incident_id
    for row in rows:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        envelope = {
            "id": row["event_id"],
            "ts": format_ts(row["created_at"]),
            "type": row["type"],
            "incident_id": incident_id,
            "actor": row["actor"],
            "payload": payload,
        }
        if row["prev_hash"] != prev_hash or next_hash(prev_hash, envelope) != row["hash"]:
            return {"valid": False, "break_at_seq": row["seq"]}
        prev_hash = row["hash"]
    return {"valid": True, "break_at_seq": None}


async def emit(
    conn: asyncpg.Connection | asyncpg.pool.PoolConnectionProxy,
    *,
    incident_id: str,
    type: str,
    actor: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Append one event to incident_id's chain and publish it on aegis:events.

    Must run with `conn` inside the same transaction as any row change the
    event describes (e.g. the incidents insert for incident.detected), so a
    crash between the two never happens.
    """
    # created_at must be the exact instant hashed into the envelope's ts, not
    # whatever Postgres's own now() resolves to a few microseconds later at
    # INSERT time; otherwise reconstructing the envelope from the row (WS
    # replay, verify-chain) reformats a different ts and the hash no longer
    # recomputes. One `now`, used for both.
    now = datetime.now(UTC)
    envelope = build_envelope(
        incident_id=incident_id, type=type, actor=actor, payload=payload, now=now
    )
    prev_hash = await conn.fetchval(
        "SELECT hash FROM aegis.incident_events WHERE incident_id = $1 ORDER BY seq DESC LIMIT 1",
        incident_id,
    )
    if prev_hash is None:
        prev_hash = incident_id
    hash_ = next_hash(prev_hash, envelope)
    await conn.execute(
        """
        INSERT INTO aegis.incident_events
            (incident_id, event_id, type, actor, payload, prev_hash, hash, created_at)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
        """,
        incident_id,
        envelope["id"],
        type,
        actor,
        json.dumps(payload),
        prev_hash,
        hash_,
        now,
    )
    redis_client = get_redis()
    try:
        await asyncio.wait_for(
            redis_client.xadd(STREAM_KEY, {"data": json.dumps(envelope)}), timeout=2
        )
    except (TimeoutError, OSError, redis.exceptions.RedisError) as exc:
        # Postgres is the source of truth for the chain; a stalled or
        # disrupted Redis (e.g. the cache_outage scenario pausing, or later
        # unpausing, the same container that carries the event stream, which
        # resets any connection the pool was mid-read on) must never lose an
        # already-committed event, only delay its live delivery. Replay on
        # reconnect covers it. redis.exceptions.RedisError is the one that
        # actually matters here: found live, a redis.exceptions.ConnectionError
        # (raised well after redis comes back from a pause, on a connection
        # the pool had open across it) is neither TimeoutError nor OSError,
        # so it used to propagate out of this function; when that happened
        # inside _mark_escalated_on_crash's transaction (aegis.agents.graph),
        # the whole transaction rolled back and the incident it was trying to
        # escalate was left stuck in its prior status forever, silently.
        logger.warning("failed to publish event %s to redis stream: %s", envelope["id"], exc)
    return envelope
