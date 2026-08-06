"""aegis.llm: the one module that owns the LLM client.

plan/01-architecture.md: all calls go through this module so the vendor is
swappable in one file. plan/03-agents-and-policy.md, Mock mode: MOCK_LLM=1
serves recorded fixtures from apps/core/fixtures/<scenario>/<node>_<n>.json,
keyed by scenario and call order, so CI and the offline demo never touch
the network.

The primitive here is a "turn": one request to the model that returns zero
or more tool calls (OpenAI-style function calling, tool_choice="required"
so a plain-text non-tool reply, which would stall the loop, is never a
valid model turn).
Nodes build a short ReAct-style loop out of turns in aegis.agents.tool_loop;
this module knows nothing about incidents, only about talking to Groq (or
replaying a fixture of having done so).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openai
from pydantic import BaseModel

logger = logging.getLogger("aegis.llm")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Approximate Groq list pricing per 1M tokens at time of writing, USD.
# Not measured; a static config dict per CLAUDE.md's phase-2 gotcha
# ("prices in one config dict, computed per run, summed per incident").
# Documented as an estimate in the phase report, not a measured claim.
PRICES_PER_MILLION: dict[str, dict[str, float]] = {
    "llama-3.1-8b-instant": {"in": 0.05, "out": 0.08},
    "llama-3.3-70b-versatile": {"in": 0.59, "out": 0.79},
    "openai/gpt-oss-120b": {"in": 0.15, "out": 0.75},
    "moonshotai/kimi-k2-instruct": {"in": 1.00, "out": 3.00},
}
DEFAULT_PRICE = {"in": 0.20, "out": 0.20}  # fallback if a model isn't in the table above

MAX_RATE_LIMIT_RETRIES = 3


def mock_enabled() -> bool:
    return os.environ.get("MOCK_LLM", "1") == "1"


def small_model() -> str:
    return os.environ.get("LLM_SMALL", "llama-3.1-8b-instant")


def large_model() -> str:
    return os.environ.get("LLM_LARGE", "llama-3.3-70b-versatile")


def _client() -> openai.AsyncOpenAI:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key and not mock_enabled():
        raise RuntimeError("GROQ_API_KEY is not set and MOCK_LLM is not 1")
    return openai.AsyncOpenAI(api_key=api_key or "mock", base_url=GROQ_BASE_URL)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True)
class AssistantTurn:
    calls: list[ToolCall]
    usage: Usage
    raw_content: str | None = None


class SchemaInvalidError(RuntimeError):
    """The model produced no tool call (or an unparseable one) twice in a row."""


def _price_for(model: str) -> dict[str, float]:
    return PRICES_PER_MILLION.get(model, DEFAULT_PRICE)


def _usage_from_response(model: str, resp: Any) -> Usage:
    usage = getattr(resp, "usage", None)
    tokens_in = getattr(usage, "prompt_tokens", 0) or 0
    tokens_out = getattr(usage, "completion_tokens", 0) or 0
    price = _price_for(model)
    cost = (tokens_in / 1_000_000) * price["in"] + (tokens_out / 1_000_000) * price["out"]
    return Usage(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=round(cost, 5))


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["schema"],
            },
        }
        for t in tools
    ]


async def _call_live(
    *, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> AssistantTurn:
    client = _client()
    openai_tools = to_openai_tools(tools)
    request_messages = list(messages)
    last_usage = Usage()

    for _schema_attempt in range(2):
        response = None
        for rate_limit_attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                # request_messages/openai_tools are built as plain dicts (this
                # module's only contract with aegis.agents.tool_loop); the
                # openai SDK's overloads want its own TypedDicts, which is a
                # shape match, not a real type mismatch.
                response = await client.chat.completions.create(  # type: ignore[call-overload]
                    model=model,
                    messages=request_messages,
                    tools=openai_tools,
                    tool_choice="required",
                    temperature=0,
                )
                break
            except openai.RateLimitError as exc:
                if rate_limit_attempt == MAX_RATE_LIMIT_RETRIES:
                    raise
                backoff = 2**rate_limit_attempt
                logger.warning(
                    "groq 429 on %s, backing off %ss (attempt %d/%d)",
                    model,
                    backoff,
                    rate_limit_attempt + 1,
                    MAX_RATE_LIMIT_RETRIES,
                    exc_info=exc,
                )
                await asyncio.sleep(backoff)
        assert response is not None

        usage = _usage_from_response(model, response)
        last_usage = Usage(
            tokens_in=last_usage.tokens_in + usage.tokens_in,
            tokens_out=last_usage.tokens_out + usage.tokens_out,
            cost_usd=round(last_usage.cost_usd + usage.cost_usd, 5),
        )
        choice = response.choices[0].message
        raw_calls = choice.tool_calls or []
        if raw_calls:
            calls = []
            for c in raw_calls:
                try:
                    args = json.loads(c.function.arguments) if c.function.arguments else {}
                except json.JSONDecodeError:
                    args = None
                if args is None:
                    break
                calls.append(ToolCall(id=c.id, name=c.function.name, arguments=args))
            else:
                return AssistantTurn(calls=calls, usage=last_usage, raw_content=choice.content)

        # No usable tool call: one retry with an explicit nudge, then give up.
        request_messages = [
            *request_messages,
            {"role": "assistant", "content": choice.content or ""},
            {
                "role": "user",
                "content": "You must respond by calling exactly one of the provided tools "
                "with valid JSON arguments. Do not respond in plain text.",
            },
        ]

    raise SchemaInvalidError(f"model {model} produced no valid tool call after retry")


@dataclass
class _FixtureCounters:
    counts: dict[tuple[str, str], int] = field(default_factory=dict)

    def next_index(self, scenario: str, node: str) -> int:
        key = (scenario, node)
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def reset(self) -> None:
        self.counts.clear()


_mock_counters = _FixtureCounters()
_record_counters = _FixtureCounters()


def reset_fixture_counters() -> None:
    """Called once per fresh graph run so fixture numbering restarts at 1.
    Module-level state; the demo runs one scenario at a time (see phase 2
    report), so this is not safe for concurrent runs of the same scenario."""
    _mock_counters.reset()
    _record_counters.reset()


def fixture_path(scenario: str, node: str, index: int) -> Path:
    return FIXTURES_DIR / scenario / f"{node}_{index}.json"


def _call_mock(*, node: str, scenario: str | None) -> AssistantTurn:
    if not scenario:
        raise RuntimeError(f"MOCK_LLM=1 but no scenario set for node {node}")
    index = _mock_counters.next_index(scenario, node)
    path = fixture_path(scenario, node, index)
    if not path.exists():
        raise FileNotFoundError(
            f"no fixture at {path}; record with `make record-fixtures SCENARIO={scenario}`"
        )
    data = json.loads(path.read_text())
    calls = [
        ToolCall(id=f"mock_{index}_{i}", name=c["name"], arguments=c["arguments"])
        for i, c in enumerate(data["calls"])
    ]
    return AssistantTurn(calls=calls, usage=Usage())


def _record(*, node: str, scenario: str | None, turn: AssistantTurn) -> None:
    if os.environ.get("RECORD_FIXTURES") != "1" or not scenario:
        return
    index = _record_counters.next_index(scenario, node)
    path = fixture_path(scenario, node, index)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"calls": [{"name": c.name, "arguments": c.arguments} for c in turn.calls]}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    logger.info("recorded fixture %s", path)


async def call_turn(
    *,
    node: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    scenario: str | None,
) -> AssistantTurn:
    """One model turn. Live: real Groq call with 429 backoff and one
    schema-invalid retry. Mock: replays the next recorded fixture for
    (scenario, node). Tools always execute live in the caller's loop
    (aegis.agents.tool_loop) regardless of MOCK_LLM; only the model's
    decisions are mocked."""
    if mock_enabled():
        return _call_mock(node=node, scenario=scenario)
    turn = await _call_live(model=model, messages=messages, tools=tools)
    _record(node=node, scenario=scenario, turn=turn)
    return turn


def response_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema for a submit-style tool's parameters, from a pydantic
    model. additionalProperties is left as pydantic emits it; nodes that
    need additionalProperties: false set model_config accordingly."""
    schema = model.model_json_schema()
    schema.pop("title", None)
    return schema
