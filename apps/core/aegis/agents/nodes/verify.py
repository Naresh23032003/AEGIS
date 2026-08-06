"""verify node: LLM_SMALL, one deterministic probe tool.
plan/03-agents-and-policy.md, Node specs. plan/phases/phase-2.md, Gotchas:
"verify uses the phase 1 detection probes, not new logic" -- passed is
always the probe tool's own all_healthy value, never the model's opinion
(aegis.agents.schemas.VerifySubmit)."""

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

    async with db.connection() as conn, conn.transaction():
        await emit(
            conn,
            incident_id=incident_id,
            type="verify.passed" if passed else "verify.failed",
            actor="agent:verify",
            payload=(
                {"evidence": [e.model_dump(mode="json") for e in verify_result.evidence]}
                if passed
                else {
                    "evidence": [e.model_dump(mode="json") for e in verify_result.evidence],
                    "loop_count": loop_count,
                }
            ),
        )

    return {"verification": verify_result.model_dump(mode="json")}
