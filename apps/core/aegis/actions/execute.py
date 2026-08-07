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

from aegis.actions import catalog, docker_ops

TOXIPROXY_URL = os.environ.get("TOXIPROXY_URL", "http://toxiproxy:8474")
# The demo shop's cache, never the event stream. This module holds no
# connection to aegis-redis at all (plan/01-architecture.md, Runtime
# topology): an action cannot touch what it cannot address.
SHOP_REDIS_URL = os.environ.get("SHOP_REDIS_URL", "redis://shop-redis:6379/0")

# apps/target/orders caches reads under order:<id>. The prefix scan predates
# the shop-redis/aegis-redis split, when a FLUSHDB here would also have wiped
# aegis:events; it stays because deleting exactly the shop's own keys is
# still narrower than emptying a whole keyspace.
CACHE_KEY_PATTERN = "order:*"

# No component in this demo actually enqueues retries yet (out of phase 3
# scope: it is a target-app feature, not a policy/security one); this key
# is the real, currently-always-empty queue flush_queue purges. A genuine
# DEL against the live stack, not a hardcoded stub, per plan/04-security.md's
# "every mechanism here is real and testable" (deviation noted in the phase
# report). Lives on shop-redis with the rest of the demo shop's keys.
RETRY_QUEUE_KEY = "aegis:orders:retry_queue"

# Containers a catalog action is allowed to name. The target services and
# the three demo dependencies they run on, and nothing else: aegis-redis,
# aegis-db, core-worker, core-api, core-executor, opa and lgtm are all
# absent on purpose. Enforced by guard_container below, independently of the
# catalog's own param enums and of OPA, so that widening an enum by accident
# still cannot hand an agent AEGIS's own infrastructure.
DEMO_CONTAINERS = frozenset(
    {
        *catalog.target_services(),
        *(f"{service}-scale-2" for service in catalog.target_services()),
        "shop-db",
        "shop-redis",
        "toxiproxy",
    }
)


class ContainerNotAllowed(ValueError):
    """A catalog action named a container outside DEMO_CONTAINERS."""


def guard_container(name: str) -> str:
    """Last check before any Docker call an action can reach. Raises rather
    than returning a flag: there is no sensible partial execution of a
    restart aimed at the wrong container."""
    if name not in DEMO_CONTAINERS:
        raise ContainerNotAllowed(f"{name} is not a demo container an action may touch")
    return name


SERVICE_URLS = {
    "target-gateway": os.environ.get("GATEWAY_URL", "http://target-gateway:9000"),
    "target-orders": os.environ.get("ORDERS_URL", "http://target-orders:9001"),
    "target-payments": os.environ.get("PAYMENTS_URL", "http://target-payments:9002"),
}
# Only target-payments carries fault toggles today (apps/target/payments/main.py);
# rollback_config best-effort clears whichever of these a service exposes.
FAULT_TOGGLE_PATHS = ("/internal/fault/error-spike", "/internal/fault/memory-leak")


async def _clear_cache() -> dict[str, Any]:
    client = redis.from_url(SHOP_REDIS_URL, decode_responses=True)
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


def _scale_clone_name(service: str) -> str:
    return f"{service}-scale-2"


async def _scale_service(service: str, replicas: int) -> dict[str, Any]:
    clone = guard_container(_scale_clone_name(guard_container(service)))
    if replicas >= 2:
        result = docker_ops.clone_and_start(service, clone)
    else:
        result = docker_ops.stop_and_remove(clone)
    return {"service": service, "replicas": replicas, **result}


async def _rollback_config(service: str) -> dict[str, Any]:
    base_url = SERVICE_URLS.get(service)
    cleared: list[str] = []
    if base_url is not None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for path in FAULT_TOGGLE_PATHS:
                try:
                    resp = await client.post(f"{base_url}{path}", json={"enabled": False})
                    resp.raise_for_status()
                    cleared.append(path)
                except httpx.HTTPError:
                    continue  # this service doesn't expose that fault toggle
    restart = docker_ops.restart_container(guard_container(service))
    return {"service": service, "cleared_faults": cleared, **restart}


async def _flush_queue() -> dict[str, Any]:
    client = redis.from_url(SHOP_REDIS_URL, decode_responses=True)
    try:
        purged = await client.delete(RETRY_QUEUE_KEY)
    finally:
        await client.aclose()
    return {"queue": RETRY_QUEUE_KEY, "purged": bool(purged)}


async def run(catalog_key: str, params: dict[str, Any]) -> dict[str, Any]:
    if catalog_key == "restart_service":
        return docker_ops.restart_container(guard_container(params["service"]))
    if catalog_key == "clear_cache":
        return await _clear_cache()
    if catalog_key == "remove_toxic":
        return await _remove_toxic(params["toxic_name"])
    if catalog_key == "restart_dependency":
        return docker_ops.restart_container(guard_container(params["service"]))
    if catalog_key == "scale_service":
        return await _scale_service(params["service"], params["replicas"])
    if catalog_key == "rollback_config":
        return await _rollback_config(params["service"])
    if catalog_key == "flush_queue":
        return await _flush_queue()
    if catalog_key == "restart_database":
        return docker_ops.restart_container(guard_container("shop-db"))
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
        # shop-redis: pausing the demo shop's cache is the outage. aegis-redis
        # keeps running, so the incident this causes can still be published.
        if action == "inject":
            return docker_ops.pause_container("shop-redis")
        return docker_ops.unpause_container("shop-redis")
    if scenario == "memory_leak" and action == "clear":
        return docker_ops.start_container("target-payments")
    raise ValueError(f"no chaos docker mapping for {scenario}/{action}")
