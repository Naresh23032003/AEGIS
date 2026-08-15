import pytest
from aegis import chaos
from aegis.api import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_healthz() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chaos_status_rejects_an_unknown_scenario() -> None:
    resp = client.get("/api/chaos/not_a_scenario")
    assert resp.status_code == 404


def test_chaos_status_reports_what_the_api_could_not_tell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fault_present stays null rather than collapsing to false when the
    executor is unreachable: a test asserting the fault is gone must not
    pass on an unanswered question."""

    async def _unknown(scenario: str) -> bool | None:
        return None

    monkeypatch.setattr(chaos, "status", _unknown)
    resp = client.get("/api/chaos/latency")
    assert resp.status_code == 200
    assert resp.json() == {"scenario": "latency", "fault_present": None}


@pytest.mark.parametrize(
    ("scenario_key", "expected"),
    [
        ("latency_target-orders", "latency"),
        ("cache_outage_target-orders", "cache_outage"),
        ("error_spike_target-payments", "error_spike"),
        ("memory_leak_target-payments", "memory_leak"),
        ("crash", "crash"),
        ("red_tier_test", None),
        ("yellow_tier_test", None),
        (None, None),
    ],
)
def test_base_scenario_strips_the_service_qualifier(
    scenario_key: str | None, expected: str | None
) -> None:
    assert chaos.base_scenario(scenario_key) == expected
