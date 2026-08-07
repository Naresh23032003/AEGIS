"""Deterministic detection loop: no LLM. plan/03-agents-and-policy.md, Detection.

Polls every 5 seconds. The two Prometheus-backed rules (latency_p95,
error_rate) must sustain past threshold for sustain_seconds before firing;
service_down fires after fail_count consecutive healthz probe failures.

A firing rule opens at most one incident per (rule, service) pair per
continuous firing episode. Once an incident exists for the pair no new one
may open, whatever that incident's status becomes (including escalated),
until the rule has evaluated clean at least once since it was created; a
fresh firing after a clean poll is a new episode and opens a new incident.
The episode flag lives in DetectionState, not in SQL, and is rebuilt from
the incidents table on worker start so a restart mid-fault does not
double-open. See plan/03-agents-and-policy.md, Detection.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from ulid import ULID

from aegis import db
from aegis.detection.probes import SERVICE_HEALTHZ, load_rules, probe_healthz, query_prometheus
from aegis.events import emit

logger = logging.getLogger("aegis.detection")

POLL_SECONDS = 5


class DetectionState:
    """In-process sustain/fail-count tracking, plus the per-(rule, service)
    firing-episode flag. Sustain windows reset on worker restart; an
    in-flight sustain window being forgotten across a restart is an
    acceptable phase 1 simplification, noted in the phase report. The
    episode flags do not reset: rebuild_episode_state() reloads them from
    the incidents table before the first poll."""

    def __init__(self) -> None:
        self.sustain_since: dict[tuple[str, str], float] = {}
        self.fail_counts: dict[str, int] = {}
        # (rule_id, service) pairs whose incident has not seen a clean
        # evaluation since it was created. While a pair is in here, the
        # rule may fire as often as it likes without opening anything new.
        self.episode_open: set[tuple[str, str]] = set()

    def episode_running(self, rule_id: str, service: str) -> bool:
        return (rule_id, service) in self.episode_open

    def mark_incident_open(self, rule_id: str, service: str) -> None:
        self.episode_open.add((rule_id, service))

    def mark_clean(self, rule_id: str, service: str) -> None:
        """One clean evaluation ends the episode, so the next firing is a
        new one and opens a new incident."""
        self.episode_open.discard((rule_id, service))


async def rebuild_episode_state(state: DetectionState) -> None:
    """Reload the episode flags from the incidents table.

    Without this a worker restart mid-fault would forget that an incident
    already exists for the pair and open a second one on its first poll.
    Resolved incidents are skipped on purpose: resolution only happens
    after verify probes came back clean, which is itself the clean
    evaluation that ends the episode.
    """
    async with db.connection() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT source_rule, unnest(affected_services) AS service "
            "FROM aegis.incidents WHERE status <> 'resolved'"
        )
    for row in rows:
        state.mark_incident_open(row["source_rule"], row["service"])
    logger.info("detection: %d firing episodes rebuilt from the incidents table", len(rows))


async def _incident_open(conn: Any, source_rule: str, service: str) -> bool:
    row = await conn.fetchrow(
        "SELECT id FROM aegis.incidents "
        "WHERE source_rule = $1 AND $2 = ANY(affected_services) "
        "AND status NOT IN ('resolved', 'escalated')",
        source_rule,
        service,
    )
    return row is not None


async def _maybe_open_incident(
    rule_id: str, service: str, snapshot: dict[str, Any], state: DetectionState
) -> None:
    if state.episode_running(rule_id, service):
        return
    async with db.connection() as conn, conn.transaction():
        # Same-transaction backstop for the runtime flag above. It only
        # catches an incident this process did not open itself, which the
        # single-worker deployment never produces; the episode rule proper
        # is the flag, because SQL alone cannot see an escalated incident's
        # episode still running.
        if await _incident_open(conn, rule_id, service):
            state.mark_incident_open(rule_id, service)
            return
        incident_id = f"inc_{ULID()}"
        title = f"{rule_id} on {service}"
        await conn.execute(
            "INSERT INTO aegis.incidents "
            "(id, title, severity, status, source_rule, affected_services, started_at) "
            "VALUES ($1, $2, NULL, 'open', $3, $4, $5)",
            incident_id,
            title,
            rule_id,
            [service],
            datetime.now(UTC),
        )
        await emit(
            conn,
            incident_id=incident_id,
            type="incident.detected",
            actor="system:detector",
            payload={"rule": rule_id, "service": service, "metrics": snapshot},
        )
        state.mark_incident_open(rule_id, service)
        logger.warning("incident %s opened: %s", incident_id, title)


async def _poll_service_down(
    client: httpx.AsyncClient, rule: dict[str, Any], state: DetectionState
) -> None:
    for service, url in SERVICE_HEALTHZ.items():
        ok = await probe_healthz(client, url)
        key = f"service_down:{service}"
        if ok:
            state.fail_counts[key] = 0
            state.mark_clean(rule["id"], service)
            continue
        state.fail_counts[key] = state.fail_counts.get(key, 0) + 1
        if state.fail_counts[key] >= rule["fail_count"]:
            await _maybe_open_incident(
                rule["id"],
                service,
                {"probe": "healthz", "fail_count": state.fail_counts[key]},
                state,
            )


async def _poll_threshold_rule(
    client: httpx.AsyncClient,
    rule: dict[str, Any],
    queries: dict[str, str],
    state: DetectionState,
    now: float,
) -> None:
    promql = queries[rule["query"]]
    try:
        values = await query_prometheus(client, promql)
    except httpx.HTTPError as exc:
        logger.warning("prometheus query failed for rule %s: %s", rule["id"], exc)
        return

    raw_threshold = rule["threshold_ms"] if "threshold_ms" in rule else rule["threshold"]
    threshold = float(raw_threshold)
    for service, value in values.items():
        key = (rule["id"], service)
        if value <= threshold:
            state.sustain_since.pop(key, None)
            state.mark_clean(rule["id"], service)
            continue
        first_seen = state.sustain_since.setdefault(key, now)
        if now - first_seen >= rule["sustain_seconds"]:
            snapshot = {"query": rule["query"], "value": value, "threshold": threshold}
            await _maybe_open_incident(rule["id"], service, snapshot, state)


async def poll_once(
    client: httpx.AsyncClient, rules_cfg: dict[str, Any], state: DetectionState
) -> None:
    now = asyncio.get_event_loop().time()
    queries = rules_cfg["queries"]
    for rule in rules_cfg["rules"]:
        if rule["id"] == "service_down":
            await _poll_service_down(client, rule, state)
        else:
            await _poll_threshold_rule(client, rule, queries, state, now)


async def run_detection_loop(stop: asyncio.Event) -> None:
    rules_cfg = load_rules()
    state = DetectionState()
    await rebuild_episode_state(state)
    async with httpx.AsyncClient() as client:
        while not stop.is_set():
            try:
                await poll_once(client, rules_cfg, state)
            except Exception:
                logger.exception("detection poll failed, continuing")
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass
