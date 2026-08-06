"""Shared probe primitives: Prometheus queries and healthz checks.

Split out of loop.py in phase 2 so the verify node's `run_verification_probes`
tool can reuse the exact same probes the detection loop uses to fire an
incident in the first place (plan/phases/phase-2.md, Gotchas: "verify uses
the phase 1 detection probes, not new logic"), rather than duplicating
PromQL text or the healthz-check shape in a second place.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml

RULES_PATH = Path(__file__).parent / "rules.yaml"

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://lgtm:9090")
SERVICE_HEALTHZ = {
    "target-gateway": f"{os.environ.get('GATEWAY_URL', 'http://target-gateway:9000')}/healthz",
    "target-orders": f"{os.environ.get('ORDERS_URL', 'http://target-orders:9001')}/healthz",
    "target-payments": f"{os.environ.get('PAYMENTS_URL', 'http://target-payments:9002')}/healthz",
}


def load_rules() -> dict[str, Any]:
    with RULES_PATH.open() as f:
        loaded: dict[str, Any] = yaml.safe_load(f)
        return loaded


async def query_prometheus(client: httpx.AsyncClient, promql: str) -> dict[str, float]:
    resp = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": promql})
    resp.raise_for_status()
    result = resp.json()["data"]["result"]
    values: dict[str, float] = {}
    for series in result:
        service = series["metric"].get("service_name")
        if service is None:
            continue
        values[service] = float(series["value"][1])
    return values


async def probe_healthz(client: httpx.AsyncClient, url: str) -> bool:
    try:
        resp = await client.get(url, timeout=2.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False
