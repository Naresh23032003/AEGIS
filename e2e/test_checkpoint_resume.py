"""plan/06-milestones.md, Phase 2 acceptance: "killing core-worker mid-run
and restarting resumes the run from checkpoint (write this as a test)."

Injects crash, waits until the graph has genuinely started (at least one
agent.run.started event on the incident), SIGKILLs core-worker mid-flight
so nothing gets a chance to shut down cleanly, restarts it, and asserts
the incident still reaches resolved. aegis.worker.Runner.resume_orphaned_runs
is what makes this possible: any incident left in `resolving` by the killed
process is resumed from its last LangGraph checkpoint on the next startup.
"""

from __future__ import annotations

import subprocess
import time

import httpx

from e2e.conftest import events_for, wait_for_incident, wait_for_resolution

COMPOSE = ["docker", "compose", "-f", "deploy/docker-compose.yml"]


def _compose(*args: str) -> None:
    subprocess.run([*COMPOSE, *args], check=True, capture_output=True)  # noqa: S603


def _wait_for_run_started(client: httpx.Client, incident_id: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = events_for(client, incident_id)
        if any(e["type"] == "agent.run.started" for e in events):
            return
        time.sleep(1)
    raise TimeoutError(f"no agent.run.started for {incident_id} within {timeout}s")


def test_killing_worker_mid_run_resumes_from_checkpoint(client: httpx.Client) -> None:
    client.post("/api/chaos/crash")
    try:
        injected_at = time.time()
        incident = wait_for_incident(
            client, source_rule="service_down", service="target-payments", after=injected_at
        )
        _wait_for_run_started(client, incident["id"])

        _compose("kill", "-s", "KILL", "core-worker")
        _compose("up", "-d", "core-worker")

        resolved = wait_for_resolution(client, incident["id"])
        assert resolved["status"] == "resolved", resolved
    finally:
        client.delete("/api/chaos/crash")
