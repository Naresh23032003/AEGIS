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
from typing import Any, Literal

import asyncpg
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from ulid import ULID

from aegis import approvals, chaos, db, evidence_pack, security
from aegis.actions.catalog import load_catalog
from aegis.events import emit, format_ts, verify_row_chain
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


def _row_to_action(row: asyncpg.Record) -> dict[str, Any]:
    params = row["params"]
    policy_result = row["policy_result"]
    result = row["result"]
    return {
        "id": row["id"],
        "incident_id": row["incident_id"],
        "catalog_key": row["catalog_key"],
        "params": json.loads(params) if isinstance(params, str) else params,
        "tier": row["tier"],
        "status": row["status"],
        "confidence": row["confidence"],
        "policy_result": (
            json.loads(policy_result) if isinstance(policy_result, str) else policy_result
        ),
        "reasoning": row["reasoning"],
        "proposed_by": row["proposed_by"],
        "executed_at": format_ts(row["executed_at"]) if row["executed_at"] else None,
        "result": json.loads(result) if isinstance(result, str) else result,
    }


def _row_to_agent_run(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "incident_id": row["incident_id"],
        "agent": row["agent"],
        "status": row["status"],
        "model": row["model"],
        "tokens_in": row["tokens_in"],
        "tokens_out": row["tokens_out"],
        "cost_usd": float(row["cost_usd"]),
        "started_at": format_ts(row["started_at"]),
        "ended_at": format_ts(row["ended_at"]) if row["ended_at"] else None,
    }


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str) -> dict[str, Any]:
    async with db.connection() as conn:
        row = await conn.fetchrow("SELECT * FROM aegis.incidents WHERE id = $1", incident_id)
        if row is None:
            raise HTTPException(status_code=404, detail="incident not found")
        action_rows = await conn.fetch(
            "SELECT * FROM aegis.actions WHERE incident_id = $1 ORDER BY id", incident_id
        )
        run_rows = await conn.fetch(
            "SELECT * FROM aegis.agent_runs WHERE incident_id = $1 ORDER BY started_at",
            incident_id,
        )
    incident = _row_to_incident(row)
    incident["actions"] = [_row_to_action(r) for r in action_rows]
    incident["agent_runs"] = [_row_to_agent_run(r) for r in run_rows]
    return incident


@app.get("/api/incidents/{incident_id}/events")
async def get_incident_events(incident_id: str) -> list[dict[str, Any]]:
    async with db.connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM aegis.incident_events WHERE incident_id = $1 ORDER BY seq ASC",
            incident_id,
        )
    return [_row_to_envelope(row) for row in rows]


@app.get("/api/chaos/{scenario}")
async def chaos_status(scenario: str) -> dict[str, Any]:
    """Whether this scenario's injected fault is present right now.

    fault_present is null when the chaos API cannot tell (executor or target
    unreachable), so "no fault" and "no answer" never collapse into each
    other. Emits nothing: reading the state of a fault is not an event.

    Added in phase 9 for the e2e suite, which asserts that a healed incident
    also left the fault gone rather than trusting one catalog_key to have
    been the right answer. No agent path reads this route.
    """
    if scenario not in chaos.SCENARIOS:
        raise HTTPException(status_code=404, detail=f"unknown scenario {scenario}")
    return {"scenario": scenario, "fault_present": await chaos.status(scenario)}


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


class RegisterKey(BaseModel):
    pubkey: str
    label: str


class SignedDecision(BaseModel):
    decision: Literal["approve", "reject", "veto"]
    pubkey: str
    signed_payload: str
    signature: str


@app.get("/api/catalog")
async def get_catalog() -> dict[str, Any]:
    catalog = load_catalog()
    return {
        key: {
            "tier": action.tier,
            "effect": action.effect,
            "rollback_key": action.rollback_key,
            "params": action.params,
        }
        for key, action in catalog.items()
    }


@app.get("/api/metrics/summary")
async def metrics_summary() -> dict[str, Any]:
    """plan/02-contracts.md: "MTTR trend, autonomy rate, escalation rate,
    cost per incident, per scenario." Not implemented in phase 2/3 (nothing
    read it yet); the console's metrics strip and /metrics page are the
    first consumers, so this is built now against the tables those phases
    already populate. `source_rule` (the detection rule id, e.g.
    latency_p95/error_rate/service_down) stands in for "scenario": the
    schema has no dedicated scenario column and several scenarios share a
    rule (plan/03's crash/memory_leak disambiguation, both service_down),
    so this is the closest real grouping key rather than an invented one.
    """
    async with db.connection() as conn:
        incidents = await conn.fetch(
            "SELECT id, source_rule, status, autonomy, mttr_seconds, resolved_at, started_at "
            "FROM aegis.incidents ORDER BY started_at ASC"
        )
        cost_rows = await conn.fetch(
            "SELECT incident_id, SUM(cost_usd) AS cost_usd FROM aegis.agent_runs "
            "GROUP BY incident_id"
        )
        loop_rows = await conn.fetch(
            "SELECT incident_id, COUNT(*) AS n FROM aegis.incident_events "
            "WHERE type IN ('verify.passed', 'verify.failed') GROUP BY incident_id"
        )
    cost_by_incident = {r["incident_id"]: float(r["cost_usd"] or 0) for r in cost_rows}
    loops_by_incident = {r["incident_id"]: r["n"] for r in loop_rows}

    resolved = [r for r in incidents if r["status"] == "resolved" and r["mttr_seconds"] is not None]
    escalated_rows = [r for r in incidents if r["status"] == "escalated"]
    active = sum(1 for r in incidents if r["status"] in ("open", "resolving", "awaiting_approval"))
    today = datetime.now(UTC).date()
    cost_today = sum(
        cost_by_incident.get(r["id"], 0.0)
        for r in incidents
        if r["started_at"] is not None and r["started_at"].astimezone(UTC).date() == today
    )
    autonomy_counts = {"auto": 0, "approved": 0, "escalated": 0}
    for r in incidents:
        if r["autonomy"] in autonomy_counts:
            autonomy_counts[r["autonomy"]] += 1
    total_terminal = len(resolved) + len(escalated_rows)
    mttr_avg = (
        sum(r["mttr_seconds"] for r in resolved) / len(resolved) if resolved else None
    )

    return {
        "mttr_avg_seconds": mttr_avg,
        "active_incidents": active,
        "cost_today_usd": round(cost_today, 5),
        "autonomy": autonomy_counts,
        "escalation_rate": (len(escalated_rows) / total_terminal) if total_terminal else 0.0,
        "mttr_trend": [
            {
                "incident_id": r["id"],
                "source_rule": r["source_rule"],
                "resolved_at": format_ts(r["resolved_at"]),
                "mttr_seconds": r["mttr_seconds"],
            }
            for r in resolved
        ],
        "cost_per_incident": [
            {
                "incident_id": r["id"],
                "source_rule": r["source_rule"],
                "cost_usd": round(cost_by_incident.get(r["id"], 0.0), 5),
            }
            for r in incidents
            if r["id"] in cost_by_incident
        ],
        "loop_iterations": [
            {"incident_id": r["id"], "loops": loops_by_incident.get(r["id"], 0)}
            for r in incidents
            if r["id"] in loops_by_incident
        ],
    }


@app.get("/api/incidents/{incident_id}/verify-chain")
async def verify_chain(incident_id: str) -> dict[str, Any]:
    async with db.connection() as conn:
        rows = await conn.fetch(
            "SELECT seq, event_id, type, actor, payload, prev_hash, hash, created_at "
            "FROM aegis.incident_events WHERE incident_id = $1 ORDER BY seq ASC",
            incident_id,
        )
    return verify_row_chain(incident_id, rows)


@app.get("/api/incidents/{incident_id}/evidence-pack")
async def get_evidence_pack(incident_id: str) -> Response:
    async with db.connection() as conn:
        data = await evidence_pack.load(conn, incident_id)
    if data is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return Response(
        content=evidence_pack.build_zip(data),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="evidence-pack-{incident_id}.zip"'
        },
    )


@app.post("/api/keys")
@limiter.limit("10/minute")
async def register_key(req: RegisterKey, request: Request, response: Response) -> dict[str, Any]:
    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "INSERT INTO aegis.approver_keys (pubkey, label) VALUES ($1, $2) "
            "ON CONFLICT (pubkey) DO UPDATE SET label = EXCLUDED.label",
            req.pubkey,
            req.label,
        )
    return {"pubkey": req.pubkey, "label": req.label}


def _parse_signed_payload(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="signed_payload is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="signed_payload must be a JSON object")
    return parsed


async def _verify_decision(action_id: str, req: SignedDecision) -> str:
    """Shared by POST /approvals and POST /veto: parses and cross-checks
    signed_payload against the URL/body, confirms the pubkey is registered,
    then verifies the Ed25519 signature and ts freshness. Returns the ts on
    success; raises HTTPException(400) on any failure. plan/02-contracts.md:
    "400 on bad signature."
    """
    parsed = _parse_signed_payload(req.signed_payload)
    if parsed.get("action_id") != action_id or parsed.get("decision") != req.decision:
        raise HTTPException(
            status_code=400, detail="signed_payload does not match this action_id/decision"
        )
    ts = parsed.get("ts")
    if not isinstance(ts, str):
        raise HTTPException(status_code=400, detail="signed_payload missing ts")
    canonical = security.signed_payload(action_id=action_id, decision=req.decision, ts=ts).decode()
    if canonical != req.signed_payload:
        raise HTTPException(status_code=400, detail="signed_payload is not canonical JSON")

    async with db.connection() as conn:
        known = await conn.fetchval(
            "SELECT 1 FROM aegis.approver_keys WHERE pubkey = $1", req.pubkey
        )
    if not known:
        raise HTTPException(
            status_code=400, detail="unknown pubkey; register it with POST /keys first"
        )

    try:
        security.verify_signature(
            pubkey_hex=req.pubkey,
            signature_hex=req.signature,
            action_id=action_id,
            decision=req.decision,
            ts=ts,
        )
    except (security.InvalidSignature, security.StaleTimestamp, security.MalformedKey) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ts


async def _record_decision(
    conn: asyncpg.Connection | asyncpg.pool.PoolConnectionProxy,
    *,
    action_id: str,
    req: SignedDecision,
) -> None:
    await conn.execute(
        "INSERT INTO aegis.approvals "
        "(id, action_id, decision, approver_pubkey, signed_payload, signature) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        f"appr_{ULID()}",
        action_id,
        req.decision,
        req.pubkey,
        req.signed_payload,
        req.signature,
    )


@app.post("/api/approvals/{action_id}")
@limiter.limit("30/minute")
async def post_approval(
    action_id: str, req: SignedDecision, request: Request, response: Response
) -> dict[str, Any]:
    if req.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be approve or reject")
    await _verify_decision(action_id, req)

    new_status = "approved" if req.decision == "approve" else "rejected"
    async with db.connection() as conn, conn.transaction():
        updated = await conn.fetchrow(
            "UPDATE aegis.actions SET status = $1 "
            "WHERE id = $2 AND status = 'awaiting_approval' RETURNING incident_id",
            new_status,
            action_id,
        )
        if updated is None:
            raise HTTPException(
                status_code=409, detail="action is not awaiting approval (already resolved)"
            )
        await _record_decision(conn, action_id=action_id, req=req)
        payload: dict[str, Any] = {
            "action_id": action_id,
            "approver_pubkey": req.pubkey,
            "signature": req.signature,
        }
        event_type = "action.approved"
        if req.decision == "reject":
            event_type = "action.rejected"
            payload["reason"] = "rejected by approver"
        envelope = await emit(
            conn,
            incident_id=updated["incident_id"],
            type=event_type,
            actor=f"human:{req.pubkey[:8]}",
            payload=payload,
        )
    return envelope


@app.post("/api/veto/{action_id}")
@limiter.limit("30/minute")
async def post_veto(
    action_id: str, req: SignedDecision, request: Request, response: Response
) -> dict[str, Any]:
    if req.decision != "veto":
        raise HTTPException(status_code=400, detail="decision must be veto")
    await _verify_decision(action_id, req)

    async with db.connection() as conn:
        action_row = await conn.fetchrow(
            "SELECT incident_id FROM aegis.actions WHERE id = $1", action_id
        )
    if action_row is None:
        raise HTTPException(status_code=404, detail="action not found")
    closes_at = await approvals.veto_closes_at(action_row["incident_id"], action_id)
    if closes_at is None or datetime.now(UTC) > closes_at:
        raise HTTPException(status_code=409, detail="veto window is not open")

    async with db.connection() as conn, conn.transaction():
        updated = await conn.fetchrow(
            "UPDATE aegis.actions SET status = 'vetoed' "
            "WHERE id = $1 AND status = 'executing' RETURNING incident_id",
            action_id,
        )
        if updated is None:
            raise HTTPException(status_code=409, detail="veto window already closed")
        await _record_decision(conn, action_id=action_id, req=req)
        envelope = await emit(
            conn,
            incident_id=updated["incident_id"],
            type="action.rejected",
            actor=f"human:{req.pubkey[:8]}",
            payload={
                "action_id": action_id,
                "approver_pubkey": req.pubkey,
                "signature": req.signature,
                "reason": "vetoed during the veto window",
            },
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
