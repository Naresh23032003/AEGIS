"""Shared helpers for the scenario e2e suite. Runs against a live compose
stack (`make up` first); not a unit test, no mocking of the stack itself.
plan/06-milestones.md, "Each scenario has an e2e test..." per plan/03.
"""

from __future__ import annotations

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
