"""Chaos injection and clearing for the five fixed scenarios.

plan/03-agents-and-policy.md, Chaos scenarios. plan/phases/phase-1.md,
Gotchas: the docker/toxiproxy command mapping lives in one module on
purpose. Phase 1 ran the Docker calls directly from core-api because
core-executor did not exist yet. Phase 2 moves every Docker-touching piece
(crash, cache_outage, and memory_leak's clear-side restart fallback) into
core-executor (aegis.actions.execute.run_chaos) and core-api loses its
Docker socket mount (plan/04-security.md, Executor sandbox: exactly one
process may hold it); this module now calls that RPC instead of
docker.from_env() directly. The Toxiproxy/HTTP-only scenarios
(latency, error_spike, memory_leak's inject side) never needed Docker and
are unchanged.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from aegis.agents import executor_client

TOXIPROXY_URL = os.environ.get("TOXIPROXY_URL", "http://toxiproxy:8474")
PAYMENTS_URL = os.environ.get("PAYMENTS_URL", "http://target-payments:9002")

SCENARIOS = {"latency", "crash", "error_spike", "memory_leak", "cache_outage"}

LATENCY_TOXIC_NAME = "orders_shopdb_latency"
LATENCY_MS = 1500


class UnknownScenario(ValueError):
    pass


async def _chaos_rpc(scenario: str, action: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{executor_client.EXECUTOR_URL}/chaos/{scenario}",
            headers=executor_client.headers(),
            json={"action": action},
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result


async def _inject_latency() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{TOXIPROXY_URL}/proxies/shopdb/toxics",
            json={
                "name": LATENCY_TOXIC_NAME,
                "type": "latency",
                "stream": "downstream",
                "attributes": {"latency": LATENCY_MS, "jitter": 0},
            },
        )
        if resp.status_code not in (200, 201, 409):
            resp.raise_for_status()
    return {"scenario": "latency", "toxic": LATENCY_TOXIC_NAME, "latency_ms": LATENCY_MS}


async def _clear_latency() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.delete(f"{TOXIPROXY_URL}/proxies/shopdb/toxics/{LATENCY_TOXIC_NAME}")
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()
    return {"scenario": "latency", "toxic": LATENCY_TOXIC_NAME}


async def _inject_crash() -> dict[str, Any]:
    result = await _chaos_rpc("crash", "inject")
    return {"scenario": "crash", **result}


async def _clear_crash() -> dict[str, Any]:
    result = await _chaos_rpc("crash", "clear")
    return {"scenario": "crash", **result}


async def _inject_error_spike() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{PAYMENTS_URL}/internal/fault/error-spike", json={"enabled": True}
        )
        resp.raise_for_status()
    return {"scenario": "error_spike", "service": "target-payments"}


async def _clear_error_spike() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{PAYMENTS_URL}/internal/fault/error-spike", json={"enabled": False}
        )
        resp.raise_for_status()
    return {"scenario": "error_spike", "service": "target-payments"}


async def _inject_memory_leak() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{PAYMENTS_URL}/internal/fault/memory-leak", json={"enabled": True}
        )
        resp.raise_for_status()
    return {"scenario": "memory_leak", "service": "target-payments"}


async def _clear_memory_leak() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(
                f"{PAYMENTS_URL}/internal/fault/memory-leak", json={"enabled": False}
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            # No restart policy on target-payments (see docker-compose.yml):
            # an OOM kill leaves it stopped so service_down has time to
            # fire. Clearing is what brings it back, standing in for the
            # restart_service action the remediation agent proposes from
            # phase 3 onward (memory_leak is not one of phase 2's two
            # working scenarios).
            await _chaos_rpc("memory_leak", "clear")
    return {"scenario": "memory_leak", "service": "target-payments"}


async def _inject_cache_outage() -> dict[str, Any]:
    result = await _chaos_rpc("cache_outage", "inject")
    return {"scenario": "cache_outage", **result}


async def _clear_cache_outage() -> dict[str, Any]:
    result = await _chaos_rpc("cache_outage", "clear")
    return {"scenario": "cache_outage", **result}


async def inject(scenario: str) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise UnknownScenario(scenario)
    if scenario == "latency":
        return await _inject_latency()
    if scenario == "crash":
        return await _inject_crash()
    if scenario == "error_spike":
        return await _inject_error_spike()
    if scenario == "memory_leak":
        return await _inject_memory_leak()
    return await _inject_cache_outage()


async def clear(scenario: str) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise UnknownScenario(scenario)
    if scenario == "latency":
        return await _clear_latency()
    if scenario == "crash":
        return await _clear_crash()
    if scenario == "error_spike":
        return await _clear_error_spike()
    if scenario == "memory_leak":
        return await _clear_memory_leak()
    return await _clear_cache_outage()
