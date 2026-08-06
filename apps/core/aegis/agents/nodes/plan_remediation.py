"""plan_remediation node: LLM_LARGE, get_catalog tool.
plan/03-agents-and-policy.md, Node specs.

The model proposes catalog_key/params/confidence/reasoning per action; this
node fills in the rest of the ActionProposal contract itself (action_id,
tier) from the catalog, never trusting the model's guess at tier
(plan/04-security.md, defense in depth)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ulid import ULID

from aegis import db, llm
from aegis.actions.catalog import CatalogError, get_action
from aegis.agents.nodes._common import run_agent_node
from aegis.agents.schemas import PlanRemediationResult
from aegis.agents.state import AgentState
from aegis.agents.tools import catalog_tool_spec
from aegis.contracts import ActionProposal
from aegis.events import emit

PROMPT = (Path(__file__).parent.parent / "prompts" / "plan_remediation.md").read_text()


async def plan_remediation(state: AgentState) -> dict[str, Any]:
    incident = state["incident"]
    incident_id = incident["id"]
    context = {
        "incident": incident,
        "hypothesis": state.get("hypothesis"),
        "confidence": state.get("confidence"),
    }

    result = await run_agent_node(
        agent="plan_remediation",
        model=llm.large_model(),
        incident_id=incident_id,
        scenario=state.get("scenario"),
        system_prompt=PROMPT,
        user_content=json.dumps(context),
        tools=[catalog_tool_spec()],
        submit_name="submit_plan",
        submit_description="Submit the proposed remediation actions.",
        response_model=PlanRemediationResult,
    )
    plan: PlanRemediationResult = result.answer  # type: ignore[assignment]

    proposals: list[dict[str, Any]] = []
    for proposed in plan.actions:
        try:
            catalog_action = get_action(proposed.catalog_key)
        except CatalogError:
            continue  # structurally impossible action, dropped before OPA ever sees it
        proposal = ActionProposal(
            action_id=f"act_{ULID()}",
            catalog_key=proposed.catalog_key,
            params=proposed.params,
            tier=catalog_action.tier,  # type: ignore[arg-type]
            confidence=proposed.confidence,
            reasoning=proposed.reasoning,
            rollback_key=catalog_action.rollback_key,
        )
        proposal_json = proposal.model_dump(mode="json")
        proposals.append(proposal_json)

        async with db.connection() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO aegis.actions "
                "(id, incident_id, catalog_key, params, tier, status, confidence, "
                "reasoning, proposed_by) "
                "VALUES ($1, $2, $3, $4::jsonb, $5, 'proposed', $6, $7, 'agent:remediation')",
                proposal.action_id,
                incident_id,
                proposal.catalog_key,
                json.dumps(proposal.params),
                proposal.tier.value,
                proposal.confidence,
                proposal.reasoning,
            )
            await emit(
                conn,
                incident_id=incident_id,
                type="action.proposed",
                actor="agent:remediation",
                payload=proposal_json,
            )

    return {"proposed_actions": proposals}
