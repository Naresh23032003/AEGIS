#!/usr/bin/env python3
"""make record-fixtures SCENARIO=latency

Runs one scenario against a live stack with a real LLM, RECORD_FIXTURES=1,
and writes apps/core/fixtures/<scenario>/<node>_<n>.json for every LLM call
made during the run. plan/03-agents-and-policy.md, Mock mode.

Swaps core-worker for a one-off replacement with RECORD_FIXTURES=1 and
MOCK_LLM=0 so this never depends on how the long-running worker's own .env
is configured, then restores the normal worker on exit (even on failure).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

COMPOSE = ["docker", "compose", "-f", "deploy/docker-compose.yml"]
API = "http://localhost:8080"
POLL_SECONDS = 3
TIMEOUT_SECONDS = 240


def run(cmd: list[str], **kwargs: object) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)  # type: ignore[arg-type]  # noqa: S603


def get_json(path: str) -> object:
    with urllib.request.urlopen(f"{API}{path}", timeout=5) as resp:  # noqa: S310
        return json.load(resp)


def post(path: str) -> None:
    req = urllib.request.Request(f"{API}{path}", method="POST", data=b"")  # noqa: S310
    urllib.request.urlopen(req, timeout=5)  # noqa: S310


def delete(path: str) -> None:
    req = urllib.request.Request(f"{API}{path}", method="DELETE")  # noqa: S310
    urllib.request.urlopen(req, timeout=5)  # noqa: S310


def _parse_ts(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def wait_resolved(scenario: str, injected_at: float) -> list[dict]:
    """Waits for every incident newly opened after injected_at (there can
    be more than one: the latency scenario fires both target-gateway and
    target-orders from the same injection) to reach a terminal status."""
    deadline = time.time() + TIMEOUT_SECONDS
    seen_new_ids: set[str] = set()
    while time.time() < deadline:
        incidents = get_json("/api/incidents?limit=20")
        new = [i for i in incidents if _parse_ts(i["started_at"]) >= injected_at - 5]  # type: ignore[index]
        for inc in new:
            seen_new_ids.add(inc["id"])
        if new and all(i["status"] in ("resolved", "escalated") for i in new):
            return new
        time.sleep(POLL_SECONDS)
    raise TimeoutError(
        f"{scenario} did not settle within {TIMEOUT_SECONDS}s (seen: {seen_new_ids})"
    )


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: record_fixtures.py <scenario>", file=sys.stderr)
        sys.exit(1)
    scenario = sys.argv[1]

    run([*COMPOSE, "stop", "core-worker"])
    run(
        [
            *COMPOSE,
            "run",
            "--rm",
            "-d",
            "--name",
            "aegis-fixture-recorder",
            "-e",
            "RECORD_FIXTURES=1",
            "-e",
            "MOCK_LLM=0",
            "core-worker",
        ]
    )
    try:
        print(f"injecting {scenario}")
        injected_at = time.time()
        post(f"/api/chaos/{scenario}")
        incidents = wait_resolved(scenario, injected_at)
        for incident in incidents:
            print(
                f"{incident['status']}: {incident['id']} "
                f"({incident['source_rule']}/{incident['affected_services']}) "
                f"mttr={incident.get('mttr_seconds')}s"
            )
    finally:
        subprocess.run(
            ["docker", "stop", "aegis-fixture-recorder"],  # noqa: S603, S607
            check=False,
            capture_output=True,
        )
        try:
            delete(f"/api/chaos/{scenario}")
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup, script still tears down
            print(f"cleanup: chaos clear failed (non-fatal): {exc}")
        run([*COMPOSE, "up", "-d", "core-worker"])


if __name__ == "__main__":
    main()
