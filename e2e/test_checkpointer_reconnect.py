"""Defect 17: the worker's checkpointer held one connection with no way to
replace it, so a single dropped connection took the worker out for good.
It stayed up, kept reporting healthy, kept claiming incidents, and
escalated every one of them on
`psycopg.OperationalError: the connection is closed`.

This kills the checkpointer's Postgres backends from the database side
while a graph run is holding one, then asserts the next incident still
heals and the container is reporting healthy again. Before the fix the
second incident always escalated. Killing backends by
application_name (aegis.agents.graph.CHECKPOINT_APP_NAME) rather than
restarting anything is what makes it the connection under test and not
the process: the worker never notices it should reconnect, which is
exactly the case that used to be unrecoverable.

Skipped under MOCK_LLM=0. The mechanism is psycopg's pool and a retry in
aegis.agents.graph, neither of which reads a model response, and the two
extra incidents would cost the live suite about 16,000 large-model tokens
against a 100,000/day cap (docs/reports/FINAL_VERIFICATION.md, phase 12).
"""

from __future__ import annotations

import os
import subprocess
import time

import httpx
import pytest

from e2e.conftest import (
    COMPOSE,
    events_for,
    wait_for_fault_cleared,
    wait_for_incident,
    wait_for_resolution,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MOCK_LLM") == "0",
    reason="checkpointer reconnect is model-independent; two extra live incidents cost tokens",
)

# aegis.agents.graph.CHECKPOINT_APP_NAME. Every checkpointer connection
# carries it, and nothing else does, so this leaves the asyncpg pool that
# core-worker uses for aegis.incidents alone.
CHECKPOINT_APP_NAME = "aegis-checkpointer"
# Interpolates only the constant above, never test input; ruff's
# SQL-injection heuristic cannot see that, hence the noqa.
_TERMINATE_SQL = (
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "  # noqa: S608
    f"WHERE application_name = '{CHECKPOINT_APP_NAME}' AND pid <> pg_backend_pid()"
)
_PSQL = ["exec", "-T", "aegis-db", "psql", "-U", "aegis", "-d", "aegis", "-p", "5433", "-tAc"]


def _terminate_checkpointer_connections() -> int:
    """Returns how many backends were killed."""
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, internal test tooling
        [*COMPOSE, *_PSQL, _TERMINATE_SQL],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return len([line for line in proc.stdout.split() if line.strip() == "t"])


def _worker_health(timeout: float = 90.0) -> str:
    """Poll compose until core-worker's healthcheck settles, and report what
    it settled on. The check reads a marker file the worker only touches
    after a checkpointer read succeeds (aegis.worker.run_health_loop), so
    "healthy" here means the checkpointer is answering, not that the
    process is alive."""
    deadline = time.time() + timeout
    status = ""
    while True:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, internal test tooling
            [*COMPOSE, "ps", "--format", "{{.Health}}", "core-worker"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        status = proc.stdout.strip()
        if status == "healthy" or time.time() >= deadline:
            return status
        time.sleep(3)


def _wait_for_run_started(client: httpx.Client, incident_id: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(e["type"] == "agent.run.started" for e in events_for(client, incident_id)):
            return
        time.sleep(1)
    raise TimeoutError(f"no agent.run.started for {incident_id} within {timeout}s")


def _crash_incident(client: httpx.Client) -> dict:
    injected_at = time.time()
    client.post("/api/chaos/crash")
    return wait_for_incident(
        client, source_rule="service_down", service="target-payments", after=injected_at
    )


def test_a_dropped_checkpointer_connection_does_not_take_the_worker_out(
    client: httpx.Client,
) -> None:
    try:
        first = _crash_incident(client)
        _wait_for_run_started(client, first["id"])

        killed = _terminate_checkpointer_connections()
        assert killed >= 1, "no checkpointer backend was connected, so nothing was tested"

        # The run holding the socket when it went is allowed to escalate:
        # what must not happen is the worker staying broken afterwards.
        wait_for_resolution(client, first["id"])

        client.delete("/api/chaos/crash")
        assert wait_for_fault_cleared(client, "crash") is False
        # One clean healthz poll ends the firing episode, otherwise the
        # second crash below is deduped into the first incident and never
        # opens one of its own (aegis.detection.loop, episode rule).
        time.sleep(15)

        second = _crash_incident(client)
        assert second["id"] != first["id"]
        resolved = wait_for_resolution(client, second["id"])
        assert resolved["status"] == "resolved", resolved

        assert _worker_health() == "healthy"
    finally:
        client.delete("/api/chaos/crash")
