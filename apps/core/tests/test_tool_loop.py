import pytest
from aegis import llm
from aegis.agents.tool_loop import ToolLoopExhausted, ToolSpec, run_tool_loop
from pydantic import BaseModel


class Answer(BaseModel):
    verdict: str


async def _fake_tool(**kwargs: object) -> str:
    return f"tool ran with {kwargs}"


async def test_tool_loop_calls_a_tool_then_submits(monkeypatch) -> None:
    turns = [
        llm.AssistantTurn(
            calls=[llm.ToolCall(id="1", name="probe", arguments={"service": "target-orders"})],
            usage=llm.Usage(tokens_in=10, tokens_out=5, cost_usd=0.001),
        ),
        llm.AssistantTurn(
            calls=[llm.ToolCall(id="2", name="submit", arguments={"verdict": "ok"})],
            usage=llm.Usage(tokens_in=8, tokens_out=3, cost_usd=0.0005),
        ),
    ]

    async def fake_call_turn(**kwargs: object) -> llm.AssistantTurn:
        return turns.pop(0)

    monkeypatch.setattr(llm, "call_turn", fake_call_turn)

    tool = ToolSpec(
        name="probe",
        description="a probe",
        schema={"type": "object", "properties": {"service": {"type": "string"}}},
        fn=_fake_tool,
        evidence_kind="metric",
    )
    result = await run_tool_loop(
        node="diagnose",
        model="x",
        system_prompt="sys",
        user_content="user",
        tools=[tool],
        submit_name="submit",
        submit_description="submit the answer",
        response_model=Answer,
        incident_id="inc_1",
        scenario="latency",
    )

    assert result.answer.verdict == "ok"
    assert result.usage.tokens_in == 18
    assert len(result.evidence) == 1
    assert result.evidence[0].source == "probe"
    assert "tool ran with" in result.evidence[0].content


async def test_tool_loop_raises_when_model_never_submits(monkeypatch) -> None:
    async def fake_call_turn(**kwargs: object) -> llm.AssistantTurn:
        return llm.AssistantTurn(calls=[], usage=llm.Usage())

    monkeypatch.setattr(llm, "call_turn", fake_call_turn)

    with pytest.raises(ToolLoopExhausted):
        await run_tool_loop(
            node="diagnose",
            model="x",
            system_prompt="sys",
            user_content="user",
            tools=[],
            submit_name="submit",
            submit_description="submit",
            response_model=Answer,
            incident_id="inc_1",
            scenario="latency",
        )
