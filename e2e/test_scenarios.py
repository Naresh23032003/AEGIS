"""Scenario e2e suite. plan/03-agents-and-policy.md, Chaos scenarios:
"Each scenario has an e2e test asserting: incident detected within 30s of
injection [see DETECT_TIMEOUT_SECONDS note in conftest.py], resolved with
expected autonomy level, MTTR under 90s (fixtures) or 150s (live LLM),
hash chain valid, expected catalog_key executed."

Phase 2 covers exactly the two scenarios that heal fully autonomously this
phase (plan/06-milestones.md, Phase 2): latency and crash. The remaining
three arrive in phase 3.
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

    chain = verify_chain(incident["id"])
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
