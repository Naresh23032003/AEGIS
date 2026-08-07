"""Shared helpers for the scenario e2e suite. Runs against a live compose
stack (`make up` first); not a unit test, no mocking of the stack itself.
plan/06-milestones.md, "Each scenario has an e2e test..." per plan/03.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from typing import Any

import httpx
import pytest

API_URL = os.environ.get("E2E_API_URL", "http://localhost:8080")
CONSOLE_URL = os.environ.get("E2E_CONSOLE_URL", "http://localhost:3000")
DETECT_TIMEOUT_SECONDS = 90  # generous: PromQL rate()[1m] windows vary, see PHASE_1_REPORT.md
RESOLVE_TIMEOUT_SECONDS = 240
# The final verification's UI walkthrough ran at this size; the console
# gates itself off below a desktop width (DesktopOnlyGate.tsx).
VIEWPORT = {"width": 1600, "height": 1000}
COMPOSE = ["docker", "compose", "-f", "deploy/docker-compose.yml"]
OPEN_STATUSES = ("open", "resolving", "awaiting_approval")
# Long enough for a PromQL rate()[1m] window to roll off after a fault
# stops, with room for the scrape interval on either side.
QUIET_TIMEOUT_SECONDS = 120

# Polls both Prometheus-backed rules from inside core-api, using detection's
# own rules.yaml and query helper rather than a second copy of the PromQL,
# and returns the (rule, service) pairs still over threshold. Runs the whole
# wait loop in the container so a quiet stack costs one `docker exec`.
_RULES_QUIET_SCRIPT = """
import asyncio, json, time
import httpx
from aegis.detection.probes import load_rules, query_prometheus

async def over_threshold(client, cfg):
    out = []
    for rule in cfg["rules"]:
        if rule["id"] == "service_down":
            continue
        promql = cfg["queries"][rule["query"]]
        raw = rule["threshold_ms"] if "threshold_ms" in rule else rule["threshold"]
        threshold = float(raw)
        for service, value in (await query_prometheus(client, promql)).items():
            if value > threshold:
                out.append([rule["id"], service, round(value, 3)])
    return out

async def main():
    deadline = time.time() + {timeout}
    cfg = load_rules()
    async with httpx.AsyncClient() as client:
        while True:
            hot = await over_threshold(client, cfg)
            if not hot or time.time() >= deadline:
                print(json.dumps(hot))
                return
            await asyncio.sleep(5)

asyncio.run(main())
"""


@pytest.fixture(autouse=True)
def _ensure_worker_running() -> None:
    """Safety net around test_checkpoint_resume.py's SIGKILL: if a prior
    test's restart raced docker and lost, later tests would otherwise fail
    for an unrelated reason (no worker to detect/remediate anything)."""
    out = subprocess.run(
        [  # noqa: S607 - "docker" resolved via PATH, internal test tooling
            "docker",
            "compose",
            "-f",
            "deploy/docker-compose.yml",
            "ps",
            "--status",
            "running",
            "--format",
            "{{.Name}}",
            "core-worker",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if "core-worker" not in out.stdout:
        # "docker" resolved via PATH; internal test tooling, not user input.
        up_cmd = ["docker", "compose", "-f", "deploy/docker-compose.yml", "up", "-d", "core-worker"]  # noqa: S607
        subprocess.run(up_cmd, check=False, capture_output=True)  # noqa: S603
        time.sleep(3)


def wait_for_rules_quiet(timeout: float = QUIET_TIMEOUT_SECONDS) -> list[list[Any]]:
    """Block until no threshold rule is firing, and report what is still hot
    if the wait runs out.

    Needed since plan/03's episode rule: a rule that never dips below its
    threshold is one continuous firing episode, so a test injecting the same
    fault a previous test just cleared would be deduped into that test's
    incident and wait forever for one of its own. The metric, not the
    incident, is what has to settle, and a rate()[1m] window takes about a
    minute to do it.
    """
    script = _RULES_QUIET_SCRIPT.replace("{timeout}", str(float(timeout)))
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, internal test tooling
        [*COMPOSE, "exec", "-T", "core-api", "python", "-"],  # noqa: S607
        input=script,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout + 60,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []  # nothing to wait on if the probe itself could not run
    hot: list[list[Any]] = json.loads(proc.stdout.strip().splitlines()[-1])
    return hot


def wait_for_no_open_incidents(client: httpx.Client, timeout: float = 240.0) -> list[str]:
    """Block until nothing is mid-run, so the console under test is showing a
    topology that will not change on its own."""
    deadline = time.time() + timeout
    while True:
        resp = client.get("/api/incidents", params={"limit": 50})
        resp.raise_for_status()
        still_open = [i["id"] for i in resp.json() if i["status"] in OPEN_STATUSES]
        if not still_open or time.time() >= deadline:
            return still_open
        time.sleep(3)


@pytest.fixture(autouse=True)
def _quiet_detection_rules() -> None:
    """Every test starts from metrics under threshold. Without this the
    suite's order decides whether a test can open an incident at all, since
    two tests injecting the same fault inside one rate() window are one
    firing episode and share one incident."""
    hot = wait_for_rules_quiet()
    if hot:
        print(f"detection rules still over threshold after the wait: {hot}")


@pytest.fixture
def client() -> httpx.Client:
    with httpx.Client(base_url=API_URL, timeout=10.0) as c:
        yield c


@pytest.fixture(scope="session")
def browser() -> Any:
    """Real Chromium for the two assertions that only exist in a browser:
    a parked approval surviving a page reload, and the forced 3D scene
    holding still under reduced motion. Both were found by hand in the
    final verification pass (defects 5 and 6); a headless browser in the
    suite is what stops them coming back. `make e2e` installs the browser
    binary first, see the Makefile's `browsers` target."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        instance = p.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


def wait_for_incident(
    client: httpx.Client, *, source_rule: str, service: str, after: float
) -> dict[str, Any]:
    deadline = time.time() + DETECT_TIMEOUT_SECONDS
    while time.time() < deadline:
        resp = client.get("/api/incidents", params={"limit": 50})
        resp.raise_for_status()
        for inc in resp.json():
            started = datetime.fromisoformat(inc["started_at"].replace("Z", "+00:00"))
            if (
                inc["source_rule"] == source_rule
                and service in inc["affected_services"]
                and started.timestamp() >= after - 5
            ):
                return inc
        time.sleep(2)
    raise TimeoutError(f"no incident for {source_rule}/{service} within {DETECT_TIMEOUT_SECONDS}s")


def wait_for_resolution(client: httpx.Client, incident_id: str) -> dict[str, Any]:
    deadline = time.time() + RESOLVE_TIMEOUT_SECONDS
    while time.time() < deadline:
        resp = client.get(f"/api/incidents/{incident_id}")
        resp.raise_for_status()
        inc = resp.json()
        if inc["status"] in ("resolved", "escalated"):
            return inc  # type: ignore[no-any-return]
        time.sleep(2)
    raise TimeoutError(f"incident {incident_id} did not resolve within {RESOLVE_TIMEOUT_SECONDS}s")


def events_for(client: httpx.Client, incident_id: str) -> list[dict[str, Any]]:
    resp = client.get(f"/api/incidents/{incident_id}/events")
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


def verify_chain(client: httpx.Client, incident_id: str) -> dict[str, Any]:
    """GET /incidents/{id}/verify-chain landed in phase 3 (PHASE_1_REPORT.md
    had this recomputing the chain out-of-band via a helper script run
    inside core-api; that stopgap is retired now that the real endpoint
    exists)."""
    resp = client.get(f"/api/incidents/{incident_id}/verify-chain")
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]
