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
DETECT_TIMEOUT_SECONDS = 90  # generous: PromQL rate()[1m] windows vary, see PHASE_1_REPORT.md
RESOLVE_TIMEOUT_SECONDS = 240


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


def verify_chain(incident_id: str) -> dict[str, Any]:
    """No GET /verify-chain endpoint until phase 3 (PHASE_1_REPORT.md,
    Deviations): recomputes the chain from the stored hash/prev_hash
    columns, which aren't exposed over HTTP, by running scripts/verify_chain.py
    inside core-api (the only place with both `aegis` importable and
    network access to aegis-db, per plan/04-security.md)."""
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, internal test tooling
        [  # noqa: S607 - "docker" is intentionally resolved via PATH
            "docker",
            "compose",
            "-f",
            "deploy/docker-compose.yml",
            "exec",
            "-T",
            "core-api",
            "python",
            "scripts/verify_chain.py",
            incident_id,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])  # type: ignore[no-any-return]
