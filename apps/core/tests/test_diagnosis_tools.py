"""query_traces span fidelity.

Defect 13 in docs/reports/FINAL_VERIFICATION.md: live diagnose blamed the
shop cache for latency that a span timing on the orders-to-database call
would have placed elsewhere. The tool could show neither, since it searched
for recent traces and reported only their ids and durations. These tests
pin what it now returns: the service's slow traces, the slowest call each
one made to each dependency, and graceful degradation when Tempo answers
badly.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from aegis.agents import tools


def _span(
    name: str,
    start_ns: int,
    end_ns: int,
    attrs: dict[str, str],
    kind: str = "SPAN_KIND_CLIENT",
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [{"key": k, "value": {"stringValue": v}} for k, v in attrs.items()],
    }


def _batch(service: str, spans: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": service}}]},
        "scopeSpans": [{"spans": spans}],
    }


# Tempo returns search hits newest-first, not slowest-first.
SEARCH = {
    "traces": [
        {"traceID": "quick", "rootServiceName": "target-gateway", "durationMs": 12},
        {"traceID": "mid_a", "rootServiceName": "target-gateway", "durationMs": 900},
        {"traceID": "slow", "rootServiceName": "target-gateway", "durationMs": 4400},
        {"traceID": "mid_b", "rootServiceName": "target-gateway", "durationMs": 800},
    ]
}
BY_DURATION = ["slow", "mid_a", "mid_b", "quick"]

# One request that waited 1.5s on the database and 0.4ms on the cache: the
# shape the latency scenario actually has, and the one the model read
# backwards without spans.
TRACE_SLOW = {
    "batches": [
        _batch(
            "target-orders",
            [
                # A FastAPI server span carries its own http.url. It calls
                # nothing, and must not be reported as calling itself.
                _span(
                    "POST /orders",
                    0,
                    1_600_000_000,
                    {"http.url": "http://target-orders:9001/orders"},
                    kind="SPAN_KIND_SERVER",
                ),
                _span(
                    "SELECT",
                    50_000_000,
                    1_552_000_000,
                    {
                        "db.system": "postgresql",
                        "net.peer.name": "shopdb-proxy",
                        "net.peer.port": "5432",
                    },
                ),
                # A second, fast call to the same database: one row per
                # dependency, and it has to be the slow one.
                _span(
                    "SELECT",
                    20_000_000,
                    20_300_000,
                    {
                        "db.system": "postgresql",
                        "net.peer.name": "shopdb-proxy",
                        "net.peer.port": "5432",
                    },
                ),
                _span(
                    "SET",
                    10_000_000,
                    10_400_000,
                    {"db.system": "redis", "net.peer.name": "shop-redis", "net.peer.port": "6379"},
                ),
            ],
        ),
        _batch(
            "target-gateway",
            [
                _span(
                    "POST",
                    0,
                    1_700_000_000,
                    {"http.url": "http://target-orders:9001/orders"},
                )
            ],
        ),
    ]
}


def _install_transport(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[str]:
    """Routes every httpx.AsyncClient the module builds through a mock
    transport, and records the paths it asked for."""
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return handler(request)

    class _Client(httpx.AsyncClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(transport=httpx.MockTransport(_handler), **kwargs)

    monkeypatch.setattr(tools.httpx, "AsyncClient", _Client)
    return seen


def _tempo(responses: dict[str, dict[str, Any]], *, traceql: dict[str, Any] | None = None) -> Any:
    """Serves /api/search twice over: `traceql` answers the slow-trace query
    (the `q` parameter), `responses["/api/search"]` the tag fallback."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/search") and "q" in request.url.params:
            return httpx.Response(200, json=traceql if traceql is not None else {"traces": []})
        for suffix, payload in responses.items():
            if request.url.path.endswith(suffix):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={})

    return handler


def _payload(output: str) -> Any:
    """Strips the quarantine wrapper the tool applies before the prompt."""
    start = output.index("{")
    return json.loads(output[start : output.rindex("}") + 1])


@pytest.mark.asyncio
async def test_query_traces_times_each_dependency_call_with_its_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _install_transport(monkeypatch, _tempo({"/api/traces/slow": TRACE_SLOW}, traceql=SEARCH))

    payload = _payload(await tools.query_traces("target-orders"))
    traces = payload["traces"]

    assert payload["searched"] == "traces from target-orders slower than 500ms"
    assert [t["trace_id"] for t in traces] == BY_DURATION
    calls = traces[0]["slowest_call_per_dependency"]
    assert [c["duration_ms"] for c in calls] == sorted(
        (c["duration_ms"] for c in calls), reverse=True
    )
    # The comparison defect 13 turned on: 1.5s waiting on the database,
    # 0.4ms waiting on the cache, both in one list.
    db_call = next(c for c in calls if c["calls"] == "postgresql shopdb-proxy:5432")
    assert db_call["service"] == "target-orders"
    assert db_call["span"] == "SELECT"
    assert db_call["duration_ms"] == pytest.approx(1502.0)
    cache_call = next(c for c in calls if c["calls"] == "redis shop-redis:6379")
    assert cache_call["duration_ms"] == pytest.approx(0.4)
    http_call = next(c for c in calls if c["service"] == "target-gateway")
    assert http_call["calls"] == "http target-orders:9001"
    # One row per dependency, and no row for a span that called nothing.
    assert len(calls) == len({c["calls"] for c in calls}) == 3
    assert all(c["span"] != "POST /orders" for c in calls)
    # The 12ms trace is listed but never opened: only the slowest few are,
    # and the two mid traces Tempo has no detail for cost their calls only.
    assert "/api/traces/quick" not in seen
    assert all("slowest_call_per_dependency" not in t for t in traces[1:])


@pytest.mark.asyncio
async def test_query_traces_survives_an_unreadable_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_transport(monkeypatch, _tempo({}, traceql=SEARCH))

    payload = _payload(await tools.query_traces("target-orders"))

    assert [t["trace_id"] for t in payload["traces"]] == BY_DURATION
    assert all("slowest_call_per_dependency" not in t for t in payload["traces"])


@pytest.mark.asyncio
async def test_query_traces_falls_back_to_recent_when_nothing_is_slow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No trace over the threshold is a finding, not an empty answer: the
    tool says so and still shows what the service did handle."""
    _install_transport(monkeypatch, _tempo({"/api/search": SEARCH}, traceql={"traces": []}))

    payload = _payload(await tools.query_traces("target-payments"))

    assert payload["searched"] == (
        "no traces from target-payments slower than 500ms; showing its most recent traces instead"
    )
    assert [t["trace_id"] for t in payload["traces"]] == BY_DURATION


@pytest.mark.asyncio
async def test_query_traces_output_is_quarantine_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_transport(monkeypatch, _tempo({"/api/traces/slow": TRACE_SLOW}, traceql=SEARCH))

    output = await tools.query_traces("target-orders")

    assert output.startswith(tools.wrap("query_traces(target-orders)", "x")[:40])
    assert "UNTRUSTED" in output.upper()
