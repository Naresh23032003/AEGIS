"""Chaos injection and clearing for the five fixed scenarios.

plan/03-agents-and-policy.md, Chaos scenarios. plan/phases/phase-1.md,
Gotchas: the docker/toxiproxy command mapping lives in this one module on
purpose. In phase 1 it runs from core-api because core-executor does not
exist yet; in phase 2 the executor calls the same functions and core-api
loses its Docker socket mount. Keep the mapping here, not spread across
call sites, so that move only touches the caller.
"""

from __future__ import annotations

import os
from typing import Any

import docker
import httpx

TOXIPROXY_URL = os.environ.get("TOXIPROXY_URL", "http://toxiproxy:8474")
PAYMENTS_URL = os.environ.get("PAYMENTS_URL", "http://target-payments:9002")

SCENARIOS = {"latency", "crash", "error_spike", "memory_leak", "cache_outage"}

LATENCY_TOXIC_NAME = "orders_shopdb_latency"
LATENCY_MS = 1500


class UnknownScenario(ValueError):
    pass


def _docker_client() -> docker.DockerClient:
    return docker.from_env()


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


def _inject_crash() -> dict[str, Any]:
    client = _docker_client()
    client.containers.get("target-payments").stop(timeout=5)
    return {"scenario": "crash", "container": "target-payments", "action": "stop"}


def _clear_crash() -> dict[str, Any]:
    client = _docker_client()
    client.containers.get("target-payments").start()
    return {"scenario": "crash", "container": "target-payments", "action": "start"}


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
            # phase 2 onward.
            _docker_client().containers.get("target-payments").start()
    return {"scenario": "memory_leak", "service": "target-payments"}


def _inject_cache_outage() -> dict[str, Any]:
    client = _docker_client()
    client.containers.get("redis").pause()
    return {"scenario": "cache_outage", "container": "redis", "action": "pause"}


def _clear_cache_outage() -> dict[str, Any]:
    client = _docker_client()
    client.containers.get("redis").unpause()
    return {"scenario": "cache_outage", "container": "redis", "action": "unpause"}


async def inject(scenario: str) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise UnknownScenario(scenario)
    if scenario == "latency":
        return await _inject_latency()
    if scenario == "crash":
        return _inject_crash()
    if scenario == "error_spike":
        return await _inject_error_spike()
    if scenario == "memory_leak":
        return await _inject_memory_leak()
    return _inject_cache_outage()


async def clear(scenario: str) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise UnknownScenario(scenario)
    if scenario == "latency":
        return await _clear_latency()
    if scenario == "crash":
        return _clear_crash()
    if scenario == "error_spike":
        return await _clear_error_spike()
    if scenario == "memory_leak":
        return await _clear_memory_leak()
    return _clear_cache_outage()
