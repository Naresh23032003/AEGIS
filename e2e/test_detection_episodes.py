"""The firing-episode rule end to end. plan/03-agents-and-policy.md,
Detection: "at most one incident per (rule, service) pair per continuous
firing episode ... until the rule has evaluated clean at least once since
that incident was created."

Defect 3 in docs/reports/FINAL_VERIFICATION.md is what this guards. The
old dedupe stopped suppressing the moment an incident escalated, so a
collateral target-gateway incident that escalated on fixture exhaustion
re-opened on the next 5s poll, and the one after that: 47 incidents in a
ten-minute fixture run, 60 in a nine-minute live run, 79% of a free-tier
daily token budget. Counting incidents per pair over a held fault is the
only assertion that catches it; the unit tests in
apps/core/tests/test_detection.py cover the state machine itself.
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime
from typing import Any

import httpx

from e2e.conftest import wait_for_incident

# How long the fault is held past the first incident. The rules engine
# polls every 5s, so 60s is 12 chances to re-open a pair; the storm in the
# final verification produced one incident per poll.
HOLD_SECONDS = 60
# error_rate reads a PromQL rate()[1m] window, so the metric stays above
# threshold for up to a minute after the fault stops. Waiting this out is
# what makes the second injection a genuinely new episode.
SETTLE_SECONDS = 75


def _started_at(incident: dict[str, Any]) -> float:
    return datetime.fromisoformat(incident["started_at"].replace("Z", "+00:00")).timestamp()


def _pairs_opened_between(client: httpx.Client, start: float, end: float) -> Counter[str]:
    resp = client.get("/api/incidents", params={"limit": 200})
    resp.raise_for_status()
    counts: Counter[str] = Counter()
    for inc in resp.json():
        if start <= _started_at(inc) <= end:
            for service in inc["affected_services"]:
                counts[f"{inc['source_rule']}/{service}"] += 1
    return counts


def test_a_held_fault_opens_one_incident_per_pair(client: httpx.Client) -> None:
    injected_at = time.time()
    client.post("/api/chaos/error_spike")
    try:
        wait_for_incident(
            client, source_rule="error_rate", service="target-payments", after=injected_at
        )
        time.sleep(HOLD_SECONDS)
    finally:
        client.delete("/api/chaos/error_spike")
    held_until = time.time()

    counts = _pairs_opened_between(client, injected_at - 2, held_until + 2)
    assert counts, "no incident opened at all during the injection"
    repeats = {pair: n for pair, n in counts.items() if n > 1}
    assert not repeats, (
        f"a pair re-opened inside one firing episode: {repeats} (all: {dict(counts)})"
    )

    # Second episode: the fault is gone, the rule has had a minute of clean
    # polls, so firing again must open a new incident rather than being
    # deduped against the first one forever.
    time.sleep(SETTLE_SECONDS)
    reinjected_at = time.time()
    client.post("/api/chaos/error_spike")
    try:
        second = wait_for_incident(
            client, source_rule="error_rate", service="target-payments", after=reinjected_at
        )
    finally:
        client.delete("/api/chaos/error_spike")

    assert _started_at(second) >= reinjected_at - 5, second
