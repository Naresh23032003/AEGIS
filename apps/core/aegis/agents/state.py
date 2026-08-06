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


RULE_TO_SCENARIO = {
    # Best-effort mapping from the firing detection rule to a chaos scenario
    # key, used only for MOCK_LLM fixture selection and for the phase 2
    # e2e suite. memory_leak also fires service_down (ambiguous with crash)
    # and is not one of phase 2's two working scenarios; disambiguating
    # that overlap is left to phase 3, noted in the phase report.
    "service_down": "crash",
    "latency_p95": "latency",
    "error_rate": "error_spike",
}


def fixture_scenario_key(*, source_rule: str, affected_services: list[str]) -> str | None:
    base = RULE_TO_SCENARIO.get(source_rule)
    if base is None:
        return None
    if not affected_services:
        return base
    return f"{base}_{affected_services[0]}"


def initial_state(*, incident: dict[str, Any], detection_snapshot: dict[str, Any]) -> AgentState:
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
            source_rule=source_rule, affected_services=incident.get("affected_services") or []
        ),
    )
