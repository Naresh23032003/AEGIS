import json
from pathlib import Path

import pytest
from aegis import llm


@pytest.fixture(autouse=True)
def _reset_counters() -> None:
    llm.reset_fixture_counters()
    yield
    llm.reset_fixture_counters()


async def test_call_turn_replays_fixture_in_order(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.setattr(llm, "FIXTURES_DIR", tmp_path)
    scenario_dir = tmp_path / "latency"
    scenario_dir.mkdir()
    (scenario_dir / "diagnose_1.json").write_text(
        json.dumps(
            {"calls": [{"name": "query_metrics", "arguments": {"service": "target-orders"}}]}
        )
    )
    (scenario_dir / "diagnose_2.json").write_text(
        json.dumps(
            {"calls": [{"name": "submit_diagnosis", "arguments": {"hypothesis": "db latency"}}]}
        )
    )

    first = await llm.call_turn(
        node="diagnose", model="x", messages=[], tools=[], scenario="latency"
    )
    assert first.calls[0].name == "query_metrics"
    assert first.usage.cost_usd == 0.0

    second = await llm.call_turn(
        node="diagnose", model="x", messages=[], tools=[], scenario="latency"
    )
    assert second.calls[0].name == "submit_diagnosis"
    assert second.calls[0].arguments == {"hypothesis": "db latency"}


async def test_call_turn_raises_when_fixture_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.setattr(llm, "FIXTURES_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        await llm.call_turn(node="triage", model="x", messages=[], tools=[], scenario="crash")


async def test_call_turn_requires_a_scenario_when_mocked(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_LLM", "1")
    with pytest.raises(RuntimeError):
        await llm.call_turn(node="triage", model="x", messages=[], tools=[], scenario=None)
