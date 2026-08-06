"""Maps a validated catalog_key to its exact mechanics. Runs inside
core-executor only. No LLM code is imported anywhere in this module or its
callers (plan/04-security.md): prompt content can never reach here, only
{catalog_key, params} that already passed aegis.actions.catalog.validate_params.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import redis.asyncio as redis

from aegis.actions import docker_ops

TOXIPROXY_URL = os.environ.get("TOXIPROXY_URL", "http://toxiproxy:8474")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# apps/target/orders caches reads under order:<id> (plan/phases/phase-2.md
# gotcha note in the phase report: redis is shared between the event stream
# and the shop cache, so clear_cache scans and deletes this prefix rather
# than FLUSHDB, which would also wipe aegis:events).
CACHE_KEY_PATTERN = "order:*"


async def _clear_cache() -> dict[str, Any]:
    client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        deleted = 0
        async for key in client.scan_iter(match=CACHE_KEY_PATTERN, count=100):
            deleted += await client.delete(key)
    finally:
        await client.aclose()
    return {"cleared_keys": deleted, "pattern": CACHE_KEY_PATTERN}


async def _remove_toxic(toxic_name: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.delete(f"{TOXIPROXY_URL}/proxies/shopdb/toxics/{toxic_name}")
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()
    return {"toxic": toxic_name, "removed": resp.status_code != 404}


async def run(catalog_key: str, params: dict[str, Any]) -> dict[str, Any]:
    if catalog_key == "restart_service":
        return docker_ops.restart_container(params["service"])
    if catalog_key == "clear_cache":
        return await _clear_cache()
    if catalog_key == "remove_toxic":
        return await _remove_toxic(params["toxic_name"])
    if catalog_key == "restart_dependency":
        return docker_ops.restart_container(params["service"])
    if catalog_key == "scale_service":
        # compose scale is out of scope for phase 2 (green tier only needs
        # to work this phase, plan/06 phase 2 build order step 3); mapping
        # exists so the catalog is complete but is untested until phase 3.
        return {"service": params["service"], "replicas": params["replicas"], "status": "stub"}
    if catalog_key == "rollback_config":
        return {"service": params["service"], "status": "stub"}
    if catalog_key == "flush_queue":
        return {"status": "stub"}
    if catalog_key == "restart_database":
        return docker_ops.restart_container("shop-db")
    raise ValueError(f"no executor mapping for {catalog_key}")


async def run_chaos(scenario: str, action: str) -> dict[str, Any]:
    """Docker-touching half of aegis.chaos, moved here in phase 2 so
    core-api no longer needs the Docker socket (plan/phases/phase-2.md,
    build order step 3: "Move the phase 1 chaos container helpers in
    here."). core-api's chaos.py now calls this over HTTP for the
    scenarios that touch a container; latency/error_spike/memory_leak's
    toggle stay in core-api since they only need Toxiproxy/HTTP, not Docker.
    """
    if scenario == "crash":
        if action == "inject":
            return docker_ops.stop_container("target-payments")
        return docker_ops.start_container("target-payments")
    if scenario == "cache_outage":
        if action == "inject":
            return docker_ops.pause_container("redis")
        return docker_ops.unpause_container("redis")
    if scenario == "memory_leak" and action == "clear":
        return docker_ops.start_container("target-payments")
    raise ValueError(f"no chaos docker mapping for {scenario}/{action}")
