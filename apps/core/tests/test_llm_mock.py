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
        node="diagnose", model="x", messages=[], tools=[], scenario="latency", incident_id="inc_1"
    )
    assert first.calls[0].name == "query_metrics"
    assert first.usage.cost_usd == 0.0

    second = await llm.call_turn(
        node="diagnose", model="x", messages=[], tools=[], scenario="latency", incident_id="inc_1"
    )
    assert second.calls[0].name == "submit_diagnosis"
    assert second.calls[0].arguments == {"hypothesis": "db latency"}


async def test_call_turn_raises_when_fixture_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.setattr(llm, "FIXTURES_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        await llm.call_turn(
            node="triage", model="x", messages=[], tools=[], scenario="crash", incident_id="inc_2"
        )


async def test_call_turn_requires_a_scenario_when_mocked(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_LLM", "1")
    with pytest.raises(RuntimeError):
        await llm.call_turn(
            node="triage", model="x", messages=[], tools=[], scenario=None, incident_id="inc_3"
        )


async def test_two_incidents_sharing_a_scenario_do_not_share_a_counter(
    tmp_path: Path, monkeypatch
) -> None:
    """Found live in phase 4: two concurrently-running incidents that
    resolve to the same scenario used to share one (scenario, node)
    counter, so the second incident's first call replayed the first
    incident's second fixture instead of its own first one. Interleaving
    the two incidents' calls here is what a shared, unkeyed counter would
    get wrong; each must independently start at fixture 1."""
    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.setattr(llm, "FIXTURES_DIR", tmp_path)
    scenario_dir = tmp_path / "crash_target-payments"
    scenario_dir.mkdir()
    (scenario_dir / "triage_1.json").write_text(
        json.dumps({"calls": [{"name": "submit_triage", "arguments": {"severity": "sev2"}}]})
    )

    # Both incidents' first call for this scenario+node must land on
    # triage_1.json. A shared (scenario, node) counter would have inc_b's
    # call land on triage_2.json (missing) instead, since inc_a's call
    # already consumed index 1.
    for incident_id in ("inc_a", "inc_b"):
        turn = await llm.call_turn(
            node="triage",
            model="x",
            messages=[],
            tools=[],
            scenario="crash_target-payments",
            incident_id=incident_id,
        )
        assert turn.calls[0].name == "submit_triage"
