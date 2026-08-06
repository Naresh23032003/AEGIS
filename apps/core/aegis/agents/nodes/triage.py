"""triage node: LLM_SMALL, no tools. plan/03-agents-and-policy.md, Node specs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aegis import db, llm
from aegis.agents.nodes._common import run_agent_node
from aegis.agents.schemas import TriageResult
from aegis.agents.state import AgentState
from aegis.events import emit

PROMPT = (Path(__file__).parent.parent / "prompts" / "triage.md").read_text()


async def triage(state: AgentState) -> dict[str, Any]:
    incident = state["incident"]
    incident_id = incident["id"]
    user_content = json.dumps(
        {"incident": incident, "detection_snapshot": state.get("detection_snapshot", {})}
    )
    result = await run_agent_node(
        agent="triage",
        model=llm.small_model(),
        incident_id=incident_id,
        scenario=state.get("scenario"),
        system_prompt=PROMPT,
        user_content=user_content,
        tools=[],
        submit_name="submit_triage",
        submit_description="Submit the triage verdict.",
        response_model=TriageResult,
    )
    triage_result: TriageResult = result.answer  # type: ignore[assignment]

    updated_incident = {
        **incident,
        "severity": triage_result.severity,
        "affected_services": triage_result.affected_services,
        "summary": triage_result.summary,
    }
    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "UPDATE aegis.incidents SET severity = $1, affected_services = $2, summary = $3 "
            "WHERE id = $4",
            triage_result.severity,
            triage_result.affected_services,
            triage_result.summary,
            incident_id,
        )
        await emit(
            conn,
            incident_id=incident_id,
            type="incident.classified",
            actor="agent:triage",
            payload={
                "severity": triage_result.severity,
                "affected_services": triage_result.affected_services,
                "summary": triage_result.summary,
            },
        )
    return {"incident": updated_incident}
