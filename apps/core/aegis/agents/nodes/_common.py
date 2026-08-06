"""Shared wrapper around aegis.agents.tool_loop for every LLM node: owns
the agent_runs row, the heartbeat ticker, and the agent.step events.
plan/03-agents-and-policy.md, Node specs: "Every tool call and thought
summary is emitted as an agent.step event, capped lengths per plan/02."
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel

from aegis.agents import runs, tool_loop


async def run_agent_node(
    *,
    agent: str,
    model: str,
    incident_id: str,
    scenario: str | None,
    system_prompt: str,
    user_content: str,
    tools: list[tool_loop.ToolSpec],
    submit_name: str,
    submit_description: str,
    response_model: type[BaseModel],
) -> tool_loop.ToolLoopResult:
    run_id = await runs.start_run(incident_id=incident_id, agent=agent, model=model)
    started = time.monotonic()

    async def on_call(tool_name: str, arguments: dict[str, Any]) -> None:
        # Emitted as each call happens, not batched at the end, so a run
        # that later fails or is quarantined still leaves a step trail
        # (plan/03: "every tool call ... is emitted as an agent.step event").
        await runs.step(
            incident_id=incident_id,
            agent=agent,
            phase="act",
            thought_summary=f"{agent} called {tool_name}",
            tool=tool_name,
            tool_args_redacted=_redact(arguments),
        )

    async with runs.heartbeat(run_id):
        try:
            result = await tool_loop.run_tool_loop(
                node=agent,
                model=model,
                system_prompt=system_prompt,
                user_content=user_content,
                tools=tools,
                submit_name=submit_name,
                submit_description=submit_description,
                response_model=response_model,
                incident_id=incident_id,
                scenario=scenario,
                on_call=on_call,
            )
        except Exception as exc:  # noqa: BLE001 - always record the failure on agent_runs
            await runs.fail_run(
                run_id=run_id, incident_id=incident_id, agent=agent, reason=str(exc)[:400]
            )
            raise

    duration_ms = int((time.monotonic() - started) * 1000)
    await runs.complete_run(
        run_id=run_id,
        incident_id=incident_id,
        agent=agent,
        tokens_in=result.usage.tokens_in,
        tokens_out=result.usage.tokens_out,
        cost_usd=result.usage.cost_usd,
        duration_ms=duration_ms,
    )
    return result


def _redact(arguments: dict[str, Any]) -> dict[str, Any]:
    # Diagnosis tool args are service names / toxic names, not secrets; kept
    # as-is. Redaction hook retained for any future tool with sensitive
    # params, per plan/02's "tool_args_redacted" payload field name.
    return arguments
