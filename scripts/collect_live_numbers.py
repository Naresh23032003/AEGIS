#!/usr/bin/env python3
"""python scripts/collect_live_numbers.py [out_path] [--scenarios a,b]

Runs each of the five chaos scenarios three times against a live stack
with the real LLM (the long-running core-worker, not a one-off container:
run this with .env's MOCK_LLM=0 and `make up` already applied), and
prints/saves the measured MTTR, cost, and autonomy per run. Source for the
phase 6 report's live-run table and the README's measured results table
(plan/06-milestones.md phase 6, plan/07-review-and-launch.md README
structure item 3): every number there must trace to this script's pasted
output.

Storm handling for cache_outage/error_spike (continuous faults that
re-trigger detection on every incident's resolution until cleared) copied
from scripts/record_fixtures.py, same reasoning documented there.

--scenarios narrows the run to a subset, for topping up one row of the
README table without spending a free-tier daily budget on the four rows
that already have three samples (phase 7 re-collected error_spike and
cache_outage this way).
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

API = "http://localhost:8080"
POLL_SECONDS = 3
TIMEOUT_SECONDS = 240
RUNS_PER_SCENARIO = 3
COOLDOWN_SECONDS = 8

SCENARIOS = ["latency", "crash", "error_spike", "memory_leak", "cache_outage"]
CLEAR_AFTER_FIRST_INCIDENT = {"cache_outage", "error_spike"}
CLEAR_GRACE_SECONDS = 10


def get_json(path: str) -> Any:
    with urllib.request.urlopen(f"{API}{path}", timeout=10) as resp:  # noqa: S310
        return json.load(resp)


def post(path: str) -> None:
    req = urllib.request.Request(f"{API}{path}", method="POST", data=b"")  # noqa: S310
    urllib.request.urlopen(req, timeout=10)  # noqa: S310


def delete(path: str) -> None:
    req = urllib.request.Request(f"{API}{path}", method="DELETE")  # noqa: S310
    urllib.request.urlopen(req, timeout=10)  # noqa: S310


def _parse_ts(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def wait_for_first_incident(injected_at: float, timeout: float = 90.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        incidents = get_json("/api/incidents?limit=20")
        new = [i for i in incidents if _parse_ts(i["started_at"]) >= injected_at - 5]
        if new:
            return min(new, key=lambda i: _parse_ts(i["started_at"]))
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"no incident opened within {timeout}s")


def wait_resolved(incident_id: str) -> dict[str, Any]:
    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        incident = get_json(f"/api/incidents/{incident_id}")
        if incident["status"] in ("resolved", "escalated"):
            return incident  # type: ignore[no-any-return]
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"{incident_id} did not settle within {TIMEOUT_SECONDS}s")


def run_once(scenario: str) -> dict[str, Any]:
    injected_at = time.time()
    post(f"/api/chaos/{scenario}")
    try:
        first = wait_for_first_incident(injected_at)
        if scenario in CLEAR_AFTER_FIRST_INCIDENT:
            time.sleep(CLEAR_GRACE_SECONDS)
            delete(f"/api/chaos/{scenario}")
        incident = wait_resolved(first["id"])
    finally:
        try:
            delete(f"/api/chaos/{scenario}")
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup
            print(f"  cleanup: chaos clear failed (non-fatal): {exc}")

    cost = sum(run["cost_usd"] for run in incident["agent_runs"])
    executed = [a["catalog_key"] for a in incident["actions"] if a["status"] == "executed"]
    return {
        "scenario": scenario,
        "incident_id": incident["id"],
        "status": incident["status"],
        "autonomy": incident["autonomy"],
        "mttr_seconds": incident["mttr_seconds"],
        "cost_usd": round(cost, 5),
        "actions_executed": executed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_path", nargs="?", default="docs/reports/live_run_results.json")
    parser.add_argument(
        "--scenarios",
        default=",".join(SCENARIOS),
        help=f"comma-separated subset of {','.join(SCENARIOS)}",
    )
    args = parser.parse_args()
    selected = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    unknown = [s for s in selected if s not in SCENARIOS]
    if unknown:
        parser.error(f"unknown scenario(s): {', '.join(unknown)}")

    results: list[dict[str, Any]] = []
    for scenario in selected:
        for run_n in range(1, RUNS_PER_SCENARIO + 1):
            print(f"=== {scenario} run {run_n}/{RUNS_PER_SCENARIO} ===")
            try:
                result = run_once(scenario)
            except TimeoutError as exc:
                print(f"  FAILED: {exc}")
                result = {
                    "scenario": scenario,
                    "incident_id": None,
                    "status": "timeout",
                    "autonomy": None,
                    "mttr_seconds": None,
                    "cost_usd": None,
                    "actions_executed": [],
                }
            print(f"  {result}")
            results.append(result)
            time.sleep(COOLDOWN_SECONDS)

    out_path = Path(args.out_path)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out_path}")

    print("\nscenario       | run | status    | autonomy  | mttr_s | cost_usd | actions")
    print("-" * 90)
    for r in results:
        print(
            f"{r['scenario']:<14} | {'':<3} | {r['status']:<9} | "
            f"{str(r['autonomy']):<9} | {str(r['mttr_seconds']):<6} | "
            f"{str(r['cost_usd']):<8} | {r['actions_executed']}"
        )


if __name__ == "__main__":
    main()
