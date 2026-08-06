"""aegis.api: FastAPI app, REST + WebSocket fanout.

plan/02-contracts.md, HTTP API and WebSocket. /healthz and /ws/events are
unprefixed (matching the WebSocket section and the phase 0 healthcheck
already wired into deploy/docker-compose.yml); everything else sits under
/api per the HTTP API table header.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from aegis import chaos, db
from aegis.events import emit, format_ts
from aegis.redis_stream import STREAM_KEY, get_redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s api %(message)s")
logger = logging.getLogger("aegis.api")

CONSOLE_ORIGIN = os.environ.get("CONSOLE_ORIGIN", "http://localhost:3000")
# synthetic incident_id chaining chaos.* events not yet tied to an incident
CHAOS_CHAIN_ID = "chaos"
WS_PING_SECONDS = 20
WS_REPLAY_WINDOW_SECONDS = 0.2


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await db.init_schema()
    yield
    await db.close_pool()


app = FastAPI(title="aegis-core-api", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,  # type: ignore[arg-type]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[CONSOLE_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _row_to_incident(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "severity": row["severity"],
        "status": row["status"],
        "source_rule": row["source_rule"],
        "affected_services": list(row["affected_services"]),
        "started_at": format_ts(row["started_at"]),
        "resolved_at": format_ts(row["resolved_at"]) if row["resolved_at"] else None,
        "mttr_seconds": row["mttr_seconds"],
        "autonomy": row["autonomy"],
        "summary": row["summary"],
    }


def _row_to_envelope(row: asyncpg.Record) -> dict[str, Any]:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {
        "id": row["event_id"],
        "ts": format_ts(row["created_at"]),
        "type": row["type"],
        "incident_id": row["incident_id"],
        "actor": row["actor"],
        "payload": payload,
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/incidents")
async def list_incidents(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    async with db.connection() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM aegis.incidents WHERE status = $1 "
                "ORDER BY started_at DESC LIMIT $2",
                status,
                limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM aegis.incidents ORDER BY started_at DESC LIMIT $1", limit
            )
    return [_row_to_incident(row) for row in rows]


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str) -> dict[str, Any]:
    async with db.connection() as conn:
        row = await conn.fetchrow("SELECT * FROM aegis.incidents WHERE id = $1", incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="incident not found")
    incident = _row_to_incident(row)
    # actions and agent_runs tables arrive in phase 2/3; empty until then.
    incident["actions"] = []
    incident["agent_runs"] = []
    return incident


@app.get("/api/incidents/{incident_id}/events")
async def get_incident_events(incident_id: str) -> list[dict[str, Any]]:
    async with db.connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM aegis.incident_events WHERE incident_id = $1 ORDER BY seq ASC",
            incident_id,
        )
    return [_row_to_envelope(row) for row in rows]


@app.post("/api/chaos/{scenario}")
@limiter.limit("10/minute")
async def inject_chaos(scenario: str, request: Request, response: Response) -> dict[str, Any]:
    if scenario not in chaos.SCENARIOS:
        raise HTTPException(status_code=404, detail=f"unknown scenario {scenario}")
    result = await chaos.inject(scenario)
    async with db.connection() as conn, conn.transaction():
        envelope = await emit(
            conn,
            incident_id=CHAOS_CHAIN_ID,
            type="chaos.injected",
            actor="system:detector",
            payload={"scenario": scenario, "params": result},
        )
    return envelope


@app.delete("/api/chaos/{scenario}")
@limiter.limit("10/minute")
async def clear_chaos(scenario: str, request: Request, response: Response) -> dict[str, Any]:
    if scenario not in chaos.SCENARIOS:
        raise HTTPException(status_code=404, detail=f"unknown scenario {scenario}")
    await chaos.clear(scenario)
    async with db.connection() as conn, conn.transaction():
        envelope = await emit(
            conn,
            incident_id=CHAOS_CHAIN_ID,
            type="chaos.cleared",
            actor="system:detector",
            payload={"scenario": scenario},
        )
    return envelope


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    await websocket.accept()

    # Optional replay handshake: {"replay_incident": "<id>"}. Give the
    # client a short window to send it before falling through to live tail.
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=WS_REPLAY_WINDOW_SECONDS)
        msg = json.loads(raw)
        incident_id = msg.get("replay_incident")
        if incident_id:
            async with db.connection() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM aegis.incident_events WHERE incident_id = $1 ORDER BY seq ASC",
                    incident_id,
                )
            for row in rows:
                await websocket.send_text(json.dumps(_row_to_envelope(row)))
    except TimeoutError:
        pass
    except WebSocketDisconnect:
        return
    except (json.JSONDecodeError, AttributeError):
        pass  # malformed handshake frame; fall through to live tail

    redis = get_redis()
    last_id = "$"
    last_ping = datetime.now(UTC)
    try:
        while True:
            entries: Any = None
            try:
                entries = await asyncio.wait_for(
                    redis.xread({STREAM_KEY: last_id}, block=2000, count=50), timeout=5
                )
            except TimeoutError:
                pass
            if entries:
                for _stream, messages in entries:
                    for message_id, fields in messages:
                        last_id = message_id
                        await websocket.send_text(fields["data"])
            if (datetime.now(UTC) - last_ping).total_seconds() > WS_PING_SECONDS:
                await websocket.send_json({"type": "ping"})
                last_ping = datetime.now(UTC)
    except WebSocketDisconnect:
        logger.info("ws client disconnected")
