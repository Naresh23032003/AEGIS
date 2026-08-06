"""diagnose node: LLM_LARGE, five diagnosis tools. plan/03-agents-and-policy.md,
Node specs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aegis import llm
from aegis.agents import tools as diagnosis_tools
from aegis.agents.nodes._common import run_agent_node
from aegis.agents.schemas import DiagnoseResult
from aegis.agents.state import AgentState

PROMPT = (Path(__file__).parent.parent / "prompts" / "diagnose.md").read_text()


async def diagnose(state: AgentState) -> dict[str, Any]:
    incident = state["incident"]
    incident_id = incident["id"]
    context: dict[str, Any] = {
        "incident": incident,
        "detection_snapshot": state.get("detection_snapshot", {}),
    }
    verification = state.get("verification")
    if verification is not None:
        context["previous_verification_failed"] = verification

    result = await run_agent_node(
        agent="diagnose",
        model=llm.large_model(),
        incident_id=incident_id,
        scenario=state.get("scenario"),
        system_prompt=PROMPT,
        user_content=json.dumps(context),
        tools=diagnosis_tools.diagnosis_tool_specs(),
        submit_name="submit_diagnosis",
        submit_description="Submit the diagnosis.",
        response_model=DiagnoseResult,
    )
    diagnosis: DiagnoseResult = result.answer  # type: ignore[assignment]

    prior_evidence = state.get("evidence", [])
    new_evidence = [e.model_dump(mode="json") for e in result.evidence]
    return {
        "hypothesis": diagnosis.hypothesis,
        "confidence": diagnosis.confidence,
        "evidence": [*prior_evidence, *new_evidence],
    }
