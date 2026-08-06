"""Generic ReAct-style tool loop shared by every LLM node.

plan/03-agents-and-policy.md, Agent graph: all LLM nodes use structured
output (tool-use forced JSON matching the contracts); a schema-invalid
response is retried once, then the run fails. Diagnosis (and, to a lesser
extent, plan_remediation and verify) may call real tools a variable number
of times before producing their final answer; this module drives that loop
uniformly so each node file only declares its tools and its answer shape.

Fixture keying (plan/phases/phase-2.md, Gotchas): one fixture file per LLM
call within a node ((scenario, node, call_index)). Tools always execute
live, even under MOCK_LLM, because they are deterministic against the
injected fault; only the model's turn (which tools to call, and the final
answer) is mocked.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from aegis import llm
from aegis.contracts import Evidence

logger = logging.getLogger("aegis.agents.tool_loop")

MAX_ITERATIONS = 10

OnCall = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any]
    fn: Callable[..., Awaitable[str]]
    evidence_kind: str | None = None  # set to collect this tool's output as Evidence


@dataclass(frozen=True)
class ToolLoopResult:
    answer: BaseModel
    usage: llm.Usage
    evidence: list[Evidence]
    transcript: list[dict[str, Any]]


class ToolLoopExhausted(RuntimeError):
    pass


async def run_tool_loop(
    *,
    node: str,
    model: str,
    system_prompt: str,
    user_content: str,
    tools: list[ToolSpec],
    submit_name: str,
    submit_description: str,
    response_model: type[BaseModel],
    incident_id: str,
    scenario: str | None,
    on_call: OnCall | None = None,
) -> ToolLoopResult:
    submit_spec = {
        "name": submit_name,
        "description": submit_description,
        "schema": llm.response_schema(response_model),
    }
    tool_specs = [{"name": t.name, "description": t.description, "schema": t.schema} for t in tools]
    by_name = {t.name: t for t in tools}

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    total_usage = llm.Usage()
    evidence: list[Evidence] = []
    transcript: list[dict[str, Any]] = []

    for _ in range(MAX_ITERATIONS):
        turn = await llm.call_turn(
            node=node,
            model=model,
            messages=messages,
            tools=[*tool_specs, submit_spec],
            scenario=scenario,
        )
        total_usage = llm.Usage(
            tokens_in=total_usage.tokens_in + turn.usage.tokens_in,
            tokens_out=total_usage.tokens_out + turn.usage.tokens_out,
            cost_usd=round(total_usage.cost_usd + turn.usage.cost_usd, 5),
        )
        transcript.append(
            {"calls": [{"name": c.name, "arguments": c.arguments} for c in turn.calls]}
        )

        submit_call = next((c for c in turn.calls if c.name == submit_name), None)
        if submit_call is not None:
            if on_call is not None:
                await on_call(submit_call.name, submit_call.arguments)
            try:
                answer = response_model.model_validate(submit_call.arguments)
            except ValidationError as exc:
                raise ToolLoopExhausted(
                    f"{node}: submit arguments failed validation: {exc}"
                ) from exc
            return ToolLoopResult(
                answer=answer, usage=total_usage, evidence=evidence, transcript=transcript
            )

        if not turn.calls:
            raise ToolLoopExhausted(f"{node}: model turn produced no tool calls and no submit")

        messages.append(
            {
                "role": "assistant",
                "content": turn.raw_content or "",
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": _dump(c.arguments)},
                    }
                    for c in turn.calls
                ],
            }
        )
        for call in turn.calls:
            if on_call is not None:
                await on_call(call.name, call.arguments)
            spec = by_name.get(call.name)
            if spec is None:
                result_text = f"unknown tool {call.name}"
            else:
                try:
                    result_text = await spec.fn(**call.arguments)
                except Exception as exc:  # noqa: BLE001 - a tool failing is data, not a crash
                    logger.warning("tool %s failed: %s", call.name, exc)
                    result_text = f"tool {call.name} failed: {exc}"
                if spec.evidence_kind is not None:
                    evidence.append(
                        Evidence(
                            kind=spec.evidence_kind,  # type: ignore[arg-type]
                            source=call.name,
                            ref=_ref(call.arguments),
                            content=result_text,
                        )
                    )
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result_text})

    raise ToolLoopExhausted(f"{node}: exceeded {MAX_ITERATIONS} tool-loop iterations")


def _dump(arguments: dict[str, Any]) -> str:
    return json.dumps(arguments)


def _ref(arguments: dict[str, Any]) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted(arguments.items())) or "none"
