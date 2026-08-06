from datetime import UTC, datetime

from aegis.contracts import (
    ActionProposal,
    EventEnvelope,
    Evidence,
    Incident,
    IncidentState,
    Kind,
    Status,
    Tier,
)


def _incident() -> Incident:
    return Incident(
        id="inc_01J000000000000000000000",
        title="p95 latency above threshold on target-orders",
        severity=None,
        status=Status.open,
        source_rule="latency_p95",
        affected_services=["target-orders"],
        started_at=datetime.now(UTC),
        resolved_at=None,
        mttr_seconds=None,
        autonomy=None,
        summary=None,
    )


def test_event_envelope_round_trip() -> None:
    envelope = EventEnvelope(
        id="01J000000000000000000000",
        ts=datetime.now(UTC),
        type="incident.detected",
        incident_id="inc_01J000000000000000000000",
        actor="system:detector",
        payload={"rule": "latency_p95"},
    )
    parsed = EventEnvelope.model_validate_json(envelope.model_dump_json())
    assert parsed == envelope


def test_incident_state_round_trip() -> None:
    state = IncidentState(
        incident=_incident(),
        evidence=[
            Evidence(
                kind=Kind.metric,
                source="query_metrics",
                ref="p95_latency{service=target-orders}",
                content="p95 rose from 80ms to 900ms over 2m",
            )
        ],
        hypothesis=None,
        proposed_actions=[
            ActionProposal(
                action_id="act_01J000000000000000000000",
                catalog_key="restart_service",
                params={"service": "target-orders"},
                tier=Tier.green,
                confidence=0.82,
                reasoning="Restart clears the connection pool exhaustion seen in evidence.",
                rollback_key=None,
            )
        ],
        executed_actions=[],
        verification=None,
        loop_count=0,
        confidence=0.82,
    )
    parsed = IncidentState.model_validate_json(state.model_dump_json())
    assert parsed == state
    assert parsed.loop_count <= 3
