"""aegis.executor_app: the FastAPI app served by core-executor.

plan/04-security.md, Executor sandbox: the only service with the Docker
socket mounted. Accepts {catalog_key, params} over internal HTTP from
core-worker, authenticated with a shared secret header; validates
independently of OPA; maps to a hardcoded docker SDK / redis / Toxiproxy
call, never a shell string. No LLM code is imported here, so prompt
content can never reach this process (aegis.llm is never imported,
directly or transitively, by anything this module imports).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from aegis import db
from aegis.actions import docker_ops, execute
from aegis.actions.catalog import CatalogError, get_action, validate_params
from aegis.detection.probes import SERVICE_HEALTHZ
from aegis.events import emit

logging.basicConfig(level=logging.INFO, format="%(asctime)s executor %(message)s")
logger = logging.getLogger("aegis.executor_app")

SHARED_SECRET = os.environ.get("EXECUTOR_SHARED_SECRET", "")
# Diagnosis-only container lookups (/stats, /state). shop-redis is here
# because the diagnose node checks whether the shop cache is paused;
# aegis-redis is not, for the same reason it is in no catalog action.
STATS_CONTAINER_NAMES = {**{s: s for s in SERVICE_HEALTHZ}, "shop-redis": "shop-redis"}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await db.init_schema()
    yield
    await db.close_pool()


app = FastAPI(title="aegis-core-executor", lifespan=lifespan)


def _check_secret(secret: str | None) -> None:
    if not SHARED_SECRET or secret != SHARED_SECRET:
        raise HTTPException(status_code=401, detail="bad or missing executor secret")


class ExecuteRequest(BaseModel):
    action_id: str
    incident_id: str
    catalog_key: str
    params: dict[str, Any]


class ChaosRequest(BaseModel):
    action: str  # inject | clear


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/execute")
async def execute_action(
    req: ExecuteRequest, x_aegis_executor_secret: str | None = Header(default=None)
) -> dict[str, Any]:
    _check_secret(x_aegis_executor_secret)
    try:
        get_action(req.catalog_key)
        validate_params(req.catalog_key, req.params)
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    started = time.monotonic()
    try:
        result = await execute.run(req.catalog_key, req.params)
        status = "executed"
    except Exception as exc:  # noqa: BLE001 - always report back, never crash the executor
        logger.exception("action %s (%s) failed", req.action_id, req.catalog_key)
        result = {"error": str(exc)}
        status = "failed"
    duration_ms = int((time.monotonic() - started) * 1000)

    async with db.connection() as conn, conn.transaction():
        await emit(
            conn,
            incident_id=req.incident_id,
            type="action.executed",
            actor="system:supervisor",
            payload={
                "action_id": req.action_id,
                "catalog_key": req.catalog_key,
                "params": req.params,
                "result": result,
                "status": status,
                "duration_ms": duration_ms,
            },
        )
    logger.info(
        "executed %s (%s) for incident %s: %s in %dms",
        req.action_id,
        req.catalog_key,
        req.incident_id,
        status,
        duration_ms,
    )
    return {"status": status, "result": result, "duration_ms": duration_ms}


@app.post("/chaos/{scenario}")
async def chaos_inject(
    scenario: str, req: ChaosRequest, x_aegis_executor_secret: str | None = Header(default=None)
) -> dict[str, Any]:
    _check_secret(x_aegis_executor_secret)
    try:
        return await execute.run_chaos(scenario, req.action)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/stats/{service}")
async def stats(
    service: str, x_aegis_executor_secret: str | None = Header(default=None)
) -> dict[str, Any]:
    _check_secret(x_aegis_executor_secret)
    container = STATS_CONTAINER_NAMES.get(service)
    if container is None:
        raise HTTPException(status_code=404, detail=f"unknown service {service}")
    try:
        result = docker_ops.container_stats(container)
    except Exception as exc:  # noqa: BLE001 - stats are best-effort diagnosis input
        result = {"container": container, "error": str(exc)}
    result["checked_at"] = datetime.now(UTC).isoformat()
    return result


@app.get("/state/{service}")
async def state(
    service: str, x_aegis_executor_secret: str | None = Header(default=None)
) -> dict[str, Any]:
    """Inspect-only container state (status/OOMKilled/exit_code), unlike
    /stats which calls the live stats API and can fail on a stopped
    container. Used to tell crash and memory_leak apart (both fire the
    same service_down rule on the same container; see aegis.agents.state)."""
    _check_secret(x_aegis_executor_secret)
    container = STATS_CONTAINER_NAMES.get(service)
    if container is None:
        raise HTTPException(status_code=404, detail=f"unknown service {service}")
    return docker_ops.container_state(container)
