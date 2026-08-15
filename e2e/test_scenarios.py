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

Phase 9 replaces "the expected catalog_key executed" with "the injected
fault is actually gone", queried from the chaos API rather than inferred
from which action ran. The phase 8 live run is why: a live diagnose blamed
the cache instead of the Toxiproxy toxic, plan_remediation proposed a
yellow restart_dependency instead of a green remove_toxic, policy allowed
it, the veto window timed out, verify passed and the incident resolved in
34s with the toxic still installed (docs/reports/FINAL_VERIFICATION.md).
The old assertion failed that run on the action's identity, which is the
right verdict for the wrong reason, and it would equally have failed a
correct heal that a live model reached by a different legal route.

The new assertion is strictly harder to satisfy. A heal that leaves the
fault in place now fails on the fault, and an unanswerable chaos API
(fault_present null) fails too rather than passing on a shrug.
"""

from __future__ import annotations

import os
import time

import httpx

from e2e.conftest import (
    events_for,
    verify_chain,
    wait_for_fault_cleared,
    wait_for_incident,
    wait_for_resolution,
)

MTTR_LIMIT = 150 if os.environ.get("MOCK_LLM") == "0" else 90


def _assert_healed(
    client: httpx.Client, *, scenario: str, source_rule: str, service: str
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
    executed = [e for e in events if e["type"] == "action.executed"]
    assert executed, "incident resolved without executing any action"

    # The heal has to have removed the fault, whichever catalog_key the
    # model picked to do it. False is the only pass: True means the
    # incident closed over a live fault, None means the chaos API could not
    # tell and the claim is unproven.
    fault_present = wait_for_fault_cleared(client, scenario)
    assert fault_present is False, (
        f"{scenario}: incident {incident['id']} resolved but fault_present="
        f"{fault_present} after actions {[e['payload']['catalog_key'] for e in executed]}"
    )

    chain = verify_chain(client, incident["id"])
    assert chain["valid"], chain


def test_latency_heals(client: httpx.Client) -> None:
    client.post("/api/chaos/latency")
    try:
        _assert_healed(
            client,
            scenario="latency",
            source_rule="latency_p95",
            service="target-orders",
        )
    finally:
        client.delete("/api/chaos/latency")


def test_crash_heals(client: httpx.Client) -> None:
    client.post("/api/chaos/crash")
    try:
        _assert_healed(
            client,
            scenario="crash",
            source_rule="service_down",
            service="target-payments",
        )
    finally:
        client.delete("/api/chaos/crash")


def test_error_spike_heals(client: httpx.Client) -> None:
    client.post("/api/chaos/error_spike")
    try:
        _assert_healed(
            client,
            scenario="error_spike",
            source_rule="error_rate",
            service="target-payments",
        )
    finally:
        client.delete("/api/chaos/error_spike")


def test_memory_leak_heals(client: httpx.Client) -> None:
    client.post("/api/chaos/memory_leak")
    try:
        _assert_healed(
            client,
            scenario="memory_leak",
            source_rule="service_down",
            service="target-payments",
        )
    finally:
        client.delete("/api/chaos/memory_leak")


def test_cache_outage_heals(client: httpx.Client) -> None:
    client.post("/api/chaos/cache_outage")
    try:
        _assert_healed(
            client,
            scenario="cache_outage",
            source_rule="latency_p95",
            service="target-orders",
        )
    finally:
        client.delete("/api/chaos/cache_outage")
