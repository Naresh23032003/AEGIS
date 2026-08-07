"""LangGraph state for one incident's durable run.

plan/03-agents-and-policy.md, Agent graph: IncidentState's fields (incident,
evidence, hypothesis, proposed_actions, executed_actions, verification,
loop_count, confidence) are the packages/contracts shape. Kept here as a
plain TypedDict of JSON-safe values (not the pydantic contract objects
directly) because that is what LangGraph's AsyncPostgresSaver serializes
most simply; nodes convert to/from the contract models at their boundaries
where a payload needs to be schema-checked (events, DB rows).

`scenario` is not part of the IncidentState contract: it is an internal
fixture-keying hint (see aegis.llm) derived from the triggering detection
rule, needed only when MOCK_LLM=1. It is qualified with the affected
service (e.g. "latency_target-orders"), not just the bare chaos scenario
name ("latency"): the latency scenario fires two simultaneous incidents
(target-gateway and target-orders both breach latency_p95 from the same
injection), each running its own concurrent graph. aegis.llm's fixture
counters are keyed by (scenario, node) only, so two concurrently-running
incidents sharing a bare "latency" key would interleave and corrupt each
other's call_index sequence, both when recording and when replaying under
MOCK_LLM=1. Qualifying by service gives each incident's run its own
fixture subdirectory and counter sequence. Noted as a deviation from the
literal apps/core/fixtures/<scenario>/... path in plan/03-agents-and-policy.md
in the phase 2 report; the top-level shape is unchanged, only the key's
content is richer than the bare scenario name.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    incident: dict[str, Any]
    detection_snapshot: dict[str, Any]
    evidence: list[dict[str, Any]]
    hypothesis: str | None
    proposed_actions: list[dict[str, Any]]
    executed_actions: list[str]
    verification: dict[str, Any] | None
    loop_count: int
    confidence: float
    scenario: str | None
    escalate_reason: str | None


RULE_TO_SCENARIO = {
    # Best-effort mapping from the firing detection rule to a chaos scenario
    # key, used only for MOCK_LLM fixture selection and for the e2e suite.
    # Two of these rule/service pairs are ambiguous on their own:
    #   - service_down fires for both crash and memory_leak on
    #     target-payments (PHASE_2_REPORT.md, Open questions).
    #   - latency_p95 fires for both latency (toxiproxy DB latency) and
    #     cache_outage (a paused shop-redis makes every cache read/write
    #     hang) on target-orders.
    # resolve_scenario_hint below breaks both ties with a live container
    # check before this table is consulted; the entries here are only the
    # fallback once that check has ruled the ambiguous alternative out (or
    # the executor is unreachable).
    "service_down": "crash",
    "latency_p95": "latency",
    "error_rate": "error_spike",
}

_SERVICE_DOWN_AMBIGUOUS_SERVICE = "target-payments"
_LATENCY_AMBIGUOUS_SERVICE = "target-orders"


async def resolve_scenario_hint(*, source_rule: str, affected_services: list[str]) -> str | None:
    """Async because disambiguating needs a live container_state call;
    kept separate from the sync fixture_scenario_key below so unit tests
    (aegis.agents.state) can exercise the pure (rule, service) -> key
    mapping without a running executor. Returns None (defer to
    RULE_TO_SCENARIO) whenever the rule/service pair isn't one of the two
    ambiguous ones above, or the disambiguating check itself fails."""
    # Import at call time: aegis.agents.executor_client is worker-side
    # only, and this keeps aegis.agents.state importable (e.g. by unit
    # tests) without pulling in an httpx client at module load.
    from aegis.agents import executor_client

    first_service = affected_services[0] if affected_services else None
    if source_rule == "service_down" and first_service == _SERVICE_DOWN_AMBIGUOUS_SERVICE:
        try:
            payments_state = await executor_client.container_state(_SERVICE_DOWN_AMBIGUOUS_SERVICE)
        except executor_client.ExecutorError:
            return None
        return "memory_leak" if payments_state.get("oom_killed") else None
    if source_rule == "latency_p95" and first_service == _LATENCY_AMBIGUOUS_SERVICE:
        try:
            redis_state = await executor_client.container_state("shop-redis")
        except executor_client.ExecutorError:
            return None
        return "cache_outage" if redis_state.get("status") == "paused" else None
    return None


def fixture_scenario_key(
    *, source_rule: str, affected_services: list[str], scenario_hint: str | None = None
) -> str | None:
    base = scenario_hint or RULE_TO_SCENARIO.get(source_rule)
    if base is None:
        return None
    if not affected_services:
        return base
    return f"{base}_{affected_services[0]}"


def initial_state(
    *,
    incident: dict[str, Any],
    detection_snapshot: dict[str, Any],
    scenario_hint: str | None = None,
) -> AgentState:
    source_rule = incident["source_rule"]
    return AgentState(
        incident=incident,
        detection_snapshot=detection_snapshot,
        evidence=[],
        hypothesis=None,
        proposed_actions=[],
        executed_actions=[],
        verification=None,
        loop_count=0,
        confidence=0.0,
        scenario=fixture_scenario_key(
            source_rule=source_rule,
            affected_services=incident.get("affected_services") or [],
            scenario_hint=scenario_hint,
        ),
        escalate_reason=None,
    )
