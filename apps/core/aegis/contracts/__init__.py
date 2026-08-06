"""Contract models generated from packages/contracts/schemas.

Regenerate with `make contracts`. Never hand-write a duplicate model for a
shape defined there; import it from here instead.
"""

from aegis.contracts.generated.action_proposal_schema import ActionProposal, Tier
from aegis.contracts.generated.event_envelope_schema import EventEnvelope
from aegis.contracts.generated.evidence_schema import Evidence, Kind
from aegis.contracts.generated.incident_schema import Autonomy, Incident, Severity, Status
from aegis.contracts.generated.incident_state_schema import IncidentState
from aegis.contracts.generated.verify_result_schema import VerifyResult

__all__ = [
    "ActionProposal",
    "Autonomy",
    "Evidence",
    "EventEnvelope",
    "Incident",
    "IncidentState",
    "Kind",
    "Severity",
    "Status",
    "Tier",
    "VerifyResult",
]
