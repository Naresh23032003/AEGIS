"""Diagnosis tools available to the diagnose node, plus the smaller
single-tool sets used by plan_remediation and verify.

plan/03-agents-and-policy.md, Node specs. plan/04-security.md, Prompt
injection defense: every tool that reads live system output (logs, traces,
config history) is wrapped in aegis.agents.quarantine.wrap before it can
enter a prompt. get_catalog and run_verification_probes read our own
static/deterministic data, not attacker-reachable system output, so they
are not quarantined.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from aegis.actions.catalog import load_catalog
from aegis.agents import executor_client
from aegis.agents.quarantine import wrap
from aegis.agents.tool_loop import ToolSpec
from aegis.detection.probes import SERVICE_HEALTHZ, load_rules, probe_healthz, query_prometheus

LOKI_URL = os.environ.get("LOKI_URL", "http://lgtm:3100")
TEMPO_URL = os.environ.get("TEMPO_URL", "http://lgtm:3200")

# Repo root is bind-mounted read-only into core-worker at /repo for
# list_recent_changes (deploy/docker-compose.yml); absent in unit tests and
# in any environment that didn't mount it, which is handled gracefully.
REPO_MOUNT = "/repo"
SERVICE_DIRS = {
    "target-gateway": "apps/target/gateway",
    "target-orders": "apps/target/orders",
    "target-payments": "apps/target/payments",
}


async def query_logs(service: str) -> str:
    now = datetime.now(UTC)
    start = now - timedelta(minutes=10)
    query = f'{{service_name="{service}"}}'
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{LOKI_URL}/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": str(int(start.timestamp() * 1e9)),
                    "end": str(int(now.timestamp() * 1e9)),
                    "limit": 200,
                    "direction": "backward",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return wrap(f"query_logs({service})", f"query failed: {exc}")

    lines = []
    for stream in data.get("data", {}).get("result", []):
        for _ts, line in stream.get("values", []):
            lines.append(line)
    content = "\n".join(lines) if lines else "no log lines in the last 10 minutes"
    return wrap(f"query_logs({service})", content)


async def query_metrics(service: str) -> str:
    rules_cfg = load_rules()
    queries = rules_cfg["queries"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        snapshot: dict[str, Any] = {}
        for name, promql in queries.items():
            try:
                values = await query_prometheus(client, promql)
            except httpx.HTTPError as exc:
                snapshot[name] = f"query failed: {exc}"
                continue
            snapshot[name] = values.get(service)
    return wrap(f"query_metrics({service})", json.dumps(snapshot, indent=2))


async def query_traces(service: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{TEMPO_URL}/api/search",
                params={"tags": f"service.name={service}", "limit": 20},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return wrap(f"query_traces({service})", f"query failed: {exc}")

    traces = data.get("traces", []) or []
    if not traces:
        return wrap(f"query_traces({service})", "no traces found")
    summary = [
        {
            "trace_id": t.get("traceID"),
            "root_service": t.get("rootServiceName"),
            "duration_ms": t.get("durationMs"),
        }
        for t in traces
    ]
    return wrap(f"query_traces({service})", json.dumps(summary, indent=2))


async def list_recent_changes(service: str) -> str:
    subdir = SERVICE_DIRS.get(service)
    if subdir is None or not Path(REPO_MOUNT).is_dir():  # noqa: ASYNC240 - trivial local check
        return wrap(f"list_recent_changes({service})", "no tracked changes available")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            REPO_MOUNT,
            "log",
            "-n",
            "5",
            "--date=iso",
            "--format=%ad %s",
            "--",
            subdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        # git isn't installed in this image (or REPO_MOUNT isn't a repo);
        # this is diagnostic evidence, not a required dependency, so a
        # missing tool degrades to "no data" rather than crashing the node.
        return wrap(f"list_recent_changes({service})", "no tracked changes available")
    stdout, _ = await proc.communicate()
    content = stdout.decode(errors="replace").strip() or "no recent changes"
    return wrap(f"list_recent_changes({service})", content)


async def get_container_stats(service: str) -> str:
    try:
        stats = await executor_client.container_stats(service)
    except executor_client.ExecutorError as exc:
        return wrap(f"get_container_stats({service})", f"stats unavailable: {exc}")
    return wrap(f"get_container_stats({service})", json.dumps(stats, indent=2))


async def get_catalog() -> str:
    catalog = load_catalog()
    summary = {
        key: {
            "tier": a.tier,
            "effect": a.effect,
            "params": list(a.params),
            "rollback_key": a.rollback_key,
        }
        for key, a in catalog.items()
    }
    return json.dumps(summary, indent=2)


VERIFY_RETRY_SECONDS = 60
VERIFY_RETRY_INTERVAL_SECONDS = 5


async def _probe_services_once(
    client: httpx.AsyncClient, service_list: list[str]
) -> dict[str, Any]:
    rules_cfg = load_rules()
    queries = rules_cfg["queries"]
    thresholds = {
        r["id"]: float(r["threshold_ms"] if "threshold_ms" in r else r["threshold"])
        for r in rules_cfg["rules"]
        if r["id"] != "service_down"
    }
    result: dict[str, Any] = {}
    for service in service_list:
        healthz_url = SERVICE_HEALTHZ.get(service)
        healthy_probe = await probe_healthz(client, healthz_url) if healthz_url else None
        metrics: dict[str, float | None] = {}
        over_threshold = False
        for rule_id, promql in queries.items():
            try:
                values = await query_prometheus(client, promql)
            except httpx.HTTPError:
                continue
            value = values.get(service)
            metrics[rule_id] = value
            threshold = thresholds.get(rule_id)
            if value is not None and threshold is not None and value > threshold:
                over_threshold = True
        result[service] = {
            "healthz_ok": healthy_probe,
            "metrics": metrics,
            "over_threshold": over_threshold,
        }
    return result


async def run_verification_probes(services: str) -> str:
    """services: comma-separated list. Reuses the exact phase 1 detection
    probes (aegis.detection.probes) so verify never invents new pass/fail
    logic; the model is instructed to relay `all_healthy` faithfully.

    plan/01-architecture.md, data flow step 6: "Verification re-probes for
    up to 60 seconds." A just-executed remediation (e.g. a container
    restart) needs a few seconds before healthz answers again and the
    Prometheus rate()[1m] windows that fed the original detection roll
    past the fault; a single instant probe would very often see stale
    unhealthy data and send the graph into an unnecessary rollback loop.
    Retries in-process here so the model only ever sees one tool call.
    """
    service_list = [s.strip() for s in services.split(",") if s.strip()]
    deadline = time.monotonic() + VERIFY_RETRY_SECONDS
    attempts = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            attempts += 1
            result = await _probe_services_once(client, service_list)
            all_healthy = all(
                r["healthz_ok"] is not False and not r["over_threshold"] for r in result.values()
            )
            if all_healthy or time.monotonic() >= deadline:
                break
            await asyncio.sleep(VERIFY_RETRY_INTERVAL_SECONDS)
    return json.dumps(
        {
            "all_healthy": all_healthy,
            "probes": result,
            "attempts": attempts,
            "checked_at": time.time(),
        }
    )


def diagnosis_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="query_logs",
            description="Fetch recent log lines for a target service from Loki.",
            schema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
                "additionalProperties": False,
            },
            fn=query_logs,
            evidence_kind="log",
        ),
        ToolSpec(
            name="query_metrics",
            description="Fetch current p95 latency and error rate for a target service from "
            "Prometheus.",
            schema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
                "additionalProperties": False,
            },
            fn=query_metrics,
            evidence_kind="metric",
        ),
        ToolSpec(
            name="query_traces",
            description="Fetch a summary of recent traces for a target service from Tempo.",
            schema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
                "additionalProperties": False,
            },
            fn=query_traces,
            evidence_kind="trace",
        ),
        ToolSpec(
            name="list_recent_changes",
            description="List the last 5 git commits that touched a target service's code.",
            schema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
                "additionalProperties": False,
            },
            fn=list_recent_changes,
            evidence_kind="log",
        ),
        ToolSpec(
            name="get_container_stats",
            description="Fetch live container resource stats (cpu, memory, status) for a "
            "target service.",
            schema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
                "additionalProperties": False,
            },
            fn=get_container_stats,
            evidence_kind="metric",
        ),
    ]


def catalog_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="get_catalog",
        description="Fetch the closed action catalog: every catalog_key, its tier, effect, "
        "and required params.",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        fn=get_catalog,
    )


def verify_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="run_verification_probes",
        description="Re-run the detection probes (healthz + the same Prometheus metrics that "
        "originally fired) against a comma-separated list of services.",
        schema={
            "type": "object",
            "properties": {"services": {"type": "string"}},
            "required": ["services"],
            "additionalProperties": False,
        },
        fn=run_verification_probes,
    )
