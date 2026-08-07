"""verify node: LLM_SMALL, one deterministic probe tool.
plan/03-agents-and-policy.md, Node specs. plan/phases/phase-2.md, Gotchas:
"verify uses the phase 1 detection probes, not new logic" -- passed is
always the probe tool's own all_healthy value, never the model's opinion
(aegis.agents.schemas.VerifySubmit).

The probe logic is unchanged in phase 9. What is new is a record, alongside
the verdict, of whether the originally injected fault was still present when
that verdict was reached, for the runs where the chaos API can tell. The
phase 8 live run had a verify pass while the Toxiproxy toxic it was supposed
to have removed was still installed (docs/reports/FINAL_VERIFICATION.md);
that was visible only by reading a container log afterwards. It is an event
payload field now. It changes no routing and reaches no prompt: the run
resolves or loops on `passed` exactly as before."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from aegis import db, llm
from aegis.agents.nodes._common import run_agent_node
from aegis.agents.schemas import VerifySubmit
from aegis.agents.state import AgentState
from aegis.agents.tools import run_verification_probes, verify_tool_spec
from aegis.contracts import Evidence, Kind, VerifyResult
from aegis.events import emit

PROMPT = (Path(__file__).parent.parent / "prompts" / "verify.md").read_text()
logger = logging.getLogger("aegis.agents.nodes.verify")

# Appended to incidents.summary when verify passed with the injected fault
# still in place, so the anomaly is visible in the incident list and the
# evidence pack without opening the timeline. Only that case is annotated:
# marking the ordinary "fault gone" outcome on every incident would be noise
# in the one field a reader skims. Both outcomes go in the event payload.
FAULT_PRESENT_MARKER = " [injected fault still present at verify]"


async def _injected_fault_present(scenario_key: str | None) -> bool | None:
    """None when there is nothing to ask about or the chaos API cannot tell.

    Imported at call time: aegis.chaos is test-scaffolding for the demo, and
    nothing in the agent path should depend on it at module load. Failures
    here are swallowed on purpose. This is an observation about a run, and
    an observation that cannot be made must never change the run's outcome.
    """
    from aegis import chaos

    scenario = chaos.base_scenario(scenario_key)
    if scenario is None:
        return None
    try:
        return await chaos.status(scenario)
    except Exception:  # noqa: BLE001 - a test signal never breaks verification
        logger.warning("could not read chaos status for %s", scenario, exc_info=True)
        return None


async def verify(state: AgentState) -> dict[str, Any]:
    incident = state["incident"]
    incident_id = incident["id"]
    services = incident.get("affected_services") or []
    loop_count = state.get("loop_count", 0)

    result = await run_agent_node(
        agent="verify",
        model=llm.small_model(),
        incident_id=incident_id,
        scenario=state.get("scenario"),
        system_prompt=PROMPT,
        user_content=json.dumps({"incident": incident, "loop_count": loop_count}),
        tools=[verify_tool_spec()],
        submit_name="submit_verification",
        submit_description="Submit the verification verdict.",
        response_model=VerifySubmit,
    )
    submitted: VerifySubmit = result.answer  # type: ignore[assignment]

    # The deterministic source of truth: re-run the same probe the LLM was
    # told to use, independent of whatever it echoed back in `passed`.
    probes_raw = await run_verification_probes(",".join(services))
    probes = json.loads(probes_raw)
    passed = bool(probes["all_healthy"])
    if submitted.passed != passed:
        logger.warning(
            "verify model said passed=%s but probes said %s for incident %s",
            submitted.passed,
            passed,
            incident_id,
        )

    fault_present = await _injected_fault_present(state.get("scenario"))
    if passed and fault_present:
        logger.warning(
            "verify passed for incident %s with the injected %s fault still present",
            incident_id,
            state.get("scenario"),
        )

    verify_result = VerifyResult(
        passed=passed,
        evidence=[
            Evidence(
                kind=Kind.metric,
                source="run_verification_probes",
                ref=",".join(services) or "none",
                content=json.dumps({**probes, "model_summary": submitted.summary}),
            )
        ],
        loop_count=loop_count,
    )

    payload: dict[str, Any] = {
        "evidence": [e.model_dump(mode="json") for e in verify_result.evidence],
        "injected_fault_present": fault_present,
    }
    if not passed:
        payload["loop_count"] = loop_count

    async with db.connection() as conn, conn.transaction():
        await emit(
            conn,
            incident_id=incident_id,
            type="verify.passed" if passed else "verify.failed",
            actor="agent:verify",
            payload=payload,
        )
        if passed and fault_present:
            # Idempotent: a re-executed node (LangGraph replay) must not
            # stack markers. Never written back onto state["incident"], so
            # no later node's prompt can see it.
            await conn.execute(
                "UPDATE aegis.incidents SET summary = "
                "replace(coalesce(summary, ''), $1, '') || $1 WHERE id = $2",
                FAULT_PRESENT_MARKER,
                incident_id,
            )

    return {"verification": verify_result.model_dump(mode="json")}
