"""The firing-episode rule from plan/03-agents-and-policy.md, Detection:
one incident per (rule, service) per continuous firing episode, whatever
the incident's status becomes, until the rule evaluates clean once.

Defect 3 in docs/reports/FINAL_VERIFICATION.md was the escalated case: the
old dedupe was a single SQL predicate that excluded 'escalated', so a
gateway incident that escalated 0.7s after opening stopped suppressing
anything and the next 5s poll opened another. 47 of them in one fixture
run, 60 in a nine-minute live run. These tests drive the loop's own poll
path with a stubbed Prometheus and a stubbed insert, so they count
openings rather than asserting on a predicate string.
"""

from __future__ import annotations

from typing import Any

import pytest
from aegis.detection import loop as loop_mod

RULES = {
    "queries": {"p95_latency": "irrelevant, query_prometheus is stubbed"},
    "rules": [
        {
            "id": "latency_p95",
            "query": "p95_latency",
            "threshold_ms": 800,
            "sustain_seconds": 0,
        }
    ],
}


class Opened:
    """Stands in for _maybe_open_incident's database half: records the
    pairs it was asked to open and flips the episode flag exactly like the
    real insert does."""

    def __init__(self) -> None:
        self.pairs: list[tuple[str, str]] = []

    async def __call__(
        self, rule_id: str, service: str, snapshot: dict[str, Any], state: Any
    ) -> None:
        if state.episode_running(rule_id, service):
            return
        self.pairs.append((rule_id, service))
        state.mark_incident_open(rule_id, service)


@pytest.fixture
def opened(monkeypatch: Any) -> Opened:
    recorder = Opened()
    monkeypatch.setattr(loop_mod, "_maybe_open_incident", recorder)
    return recorder


def _values(monkeypatch: Any, series: list[dict[str, float]]) -> None:
    """Feed poll_once a scripted sequence of PromQL results, one per poll."""
    remaining = list(series)

    async def fake_query(client: Any, promql: str) -> dict[str, float]:
        return remaining.pop(0)

    monkeypatch.setattr(loop_mod, "query_prometheus", fake_query)


async def _poll(times: int, state: loop_mod.DetectionState) -> None:
    for _ in range(times):
        await loop_mod.poll_once(None, RULES, state)  # type: ignore[arg-type]


async def test_a_continuous_episode_opens_exactly_one_incident(
    monkeypatch: Any, opened: Opened
) -> None:
    over = {"target-orders": 2400.0}
    _values(monkeypatch, [over] * 12)
    state = loop_mod.DetectionState()

    await _poll(12, state)

    assert opened.pairs == [("latency_p95", "target-orders")]


async def test_a_clean_poll_ends_the_episode_and_the_next_firing_reopens(
    monkeypatch: Any, opened: Opened
) -> None:
    over = {"target-orders": 2400.0}
    under = {"target-orders": 120.0}
    _values(monkeypatch, [over, over, under, over, over])
    state = loop_mod.DetectionState()

    await _poll(5, state)

    assert opened.pairs == [
        ("latency_p95", "target-orders"),
        ("latency_p95", "target-orders"),
    ]


async def test_an_escalated_incident_still_suppresses_its_own_episode(
    monkeypatch: Any, opened: Opened
) -> None:
    """The regression itself. The incident's status is irrelevant to the
    flag, so escalating changes nothing until a clean poll lands."""
    over = {"target-gateway": 2400.0}
    _values(monkeypatch, [over] * 8)
    state = loop_mod.DetectionState()

    await _poll(1, state)
    # ... the run escalates here. Nothing in the loop is told about it.
    await _poll(7, state)

    assert opened.pairs == [("latency_p95", "target-gateway")]


async def test_each_service_gets_its_own_episode(monkeypatch: Any, opened: Opened) -> None:
    both = {"target-orders": 2400.0, "target-gateway": 1900.0}
    _values(monkeypatch, [both] * 6)
    state = loop_mod.DetectionState()

    await _poll(6, state)

    assert sorted(opened.pairs) == [
        ("latency_p95", "target-gateway"),
        ("latency_p95", "target-orders"),
    ]


async def test_rebuild_blocks_a_restarted_worker_from_double_opening(
    monkeypatch: Any, opened: Opened
) -> None:
    """A worker that restarts mid-fault must not reopen what it already
    opened. rebuild_episode_state reloads the flags from the incidents
    table; here the row is the escalated gateway incident."""

    class FakeConn:
        async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
            assert "status <> 'resolved'" in query
            return [{"source_rule": "latency_p95", "service": "target-gateway"}]

    class FakeConnCtx:
        async def __aenter__(self) -> FakeConn:
            return FakeConn()

        async def __aexit__(self, *exc: object) -> bool:
            return False

    monkeypatch.setattr(loop_mod.db, "connection", lambda: FakeConnCtx())

    over = {"target-gateway": 2400.0}
    _values(monkeypatch, [over] * 6)
    state = loop_mod.DetectionState()
    await loop_mod.rebuild_episode_state(state)

    await _poll(6, state)

    assert opened.pairs == []


async def test_service_down_gets_the_same_episode_treatment(monkeypatch: Any) -> None:
    """The healthz path keeps its own counter, so it needs its own case:
    a passing probe is the clean evaluation that ends the episode."""
    recorder = Opened()
    monkeypatch.setattr(loop_mod, "_maybe_open_incident", recorder)
    probes = iter([False] * 6 + [True] + [False] * 6)

    async def fake_probe(client: Any, url: str) -> bool:
        return next(probes)

    monkeypatch.setattr(loop_mod, "probe_healthz", fake_probe)
    monkeypatch.setattr(loop_mod, "SERVICE_HEALTHZ", {"target-payments": "http://x/healthz"})

    rules = {"queries": {}, "rules": [{"id": "service_down", "fail_count": 3}]}
    state = loop_mod.DetectionState()
    for _ in range(13):
        await loop_mod.poll_once(None, rules, state)  # type: ignore[arg-type]

    assert recorder.pairs == [
        ("service_down", "target-payments"),
        ("service_down", "target-payments"),
    ]
