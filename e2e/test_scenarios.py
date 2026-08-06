"""Scenario e2e suite. plan/03-agents-and-policy.md, Chaos scenarios:
"Each scenario has an e2e test asserting: incident detected within 30s of
injection [see DETECT_TIMEOUT_SECONDS note in conftest.py], resolved with
expected autonomy level, MTTR under 90s (fixtures) or 150s (live LLM),
hash chain valid, expected catalog_key executed. These five tests are the
project's definition of working."

Phase 2 covered latency and crash, the two that heal fully autonomously
with no policy engine at all. Phase 3 adds the remaining three, each
exercising a different part of the tier machinery: error_spike and
cache_outage are yellow tier (their veto window opens and times out
unvetoed, since nothing here vetoes them), and memory_leak is
service_down's other cause (aegis.agents.state's crash/memory_leak
disambiguation).
"""

from __future__ import annotations

import os
import time

import httpx

from e2e.conftest import events_for, verify_chain, wait_for_incident, wait_for_resolution

MTTR_LIMIT = 150 if os.environ.get("MOCK_LLM") == "0" else 90


def _assert_healed(
    client: httpx.Client, *, source_rule: str, service: str, expected_catalog_key: str
) -> None:
    injected_at = time.time()
    incident = wait_for_incident(
        client, source_rule=source_rule, service=service, after=injected_at
    )
    resolved = wait_for_resolution(client, incident["id"])

    assert resolved["status"] == "resolved", resolved
    assert resolved["autonomy"] == "auto", resolved
    assert resolved["mttr_seconds"] is not None
    assert resolved["mttr_seconds"] < MTTR_LIMIT, resolved

    events = events_for(client, incident["id"])
    executed_keys = [e["payload"]["catalog_key"] for e in events if e["type"] == "action.executed"]
    assert expected_catalog_key in executed_keys, executed_keys

    chain = verify_chain(client, incident["id"])
    assert chain["valid"], chain


def test_latency_heals(client: httpx.Client) -> None:
    client.post("/api/chaos/latency")
    try:
        _assert_healed(
            client,
            source_rule="latency_p95",
            service="target-orders",
            expected_catalog_key="remove_toxic",
        )
    finally:
        client.delete("/api/chaos/latency")


def test_crash_heals(client: httpx.Client) -> None:
    client.post("/api/chaos/crash")
    try:
        _assert_healed(
            client,
            source_rule="service_down",
            service="target-payments",
            expected_catalog_key="restart_service",
        )
    finally:
        client.delete("/api/chaos/crash")


def test_error_spike_heals(client: httpx.Client) -> None:
    client.post("/api/chaos/error_spike")
    try:
        _assert_healed(
            client,
            source_rule="error_rate",
            service="target-payments",
            expected_catalog_key="rollback_config",
        )
    finally:
        client.delete("/api/chaos/error_spike")


def test_memory_leak_heals(client: httpx.Client) -> None:
    client.post("/api/chaos/memory_leak")
    try:
        _assert_healed(
            client,
            source_rule="service_down",
            service="target-payments",
            expected_catalog_key="restart_service",
        )
    finally:
        client.delete("/api/chaos/memory_leak")


def test_cache_outage_heals(client: httpx.Client) -> None:
    client.post("/api/chaos/cache_outage")
    try:
        _assert_healed(
            client,
            source_rule="latency_p95",
            service="target-orders",
            expected_catalog_key="restart_dependency",
        )
    finally:
        client.delete("/api/chaos/cache_outage")
