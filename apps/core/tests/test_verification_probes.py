"""Verification probe threshold comparisons.

Defect 18 in docs/reports/FINAL_VERIFICATION.md: verification probe threshold
lookup keyed rules by rule id ('latency_p95') rather than query key ('p95_latency'),
preventing threshold comparison for queries where rule id differed from query key.
"""

from __future__ import annotations

import httpx
import pytest
from aegis.agents import tools


@pytest.mark.asyncio
async def test_probe_services_once_p95_over_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """p95 of 10,000ms against a 1,000ms threshold sets over_threshold to true."""

    async def fake_query(client: httpx.AsyncClient, promql: str) -> dict[str, float]:
        if "histogram_quantile" in promql:
            return {"target-orders": 10000.0}
        return {"target-orders": 0.0}

    async def fake_healthz(client: httpx.AsyncClient, url: str) -> bool:
        return True

    monkeypatch.setattr(tools, "query_prometheus", fake_query)
    monkeypatch.setattr(tools, "probe_healthz", fake_healthz)

    async with httpx.AsyncClient() as client:
        result = await tools._probe_services_once(client, ["target-orders"])

    assert result["target-orders"]["metrics"]["p95_latency"] == 10000.0
    assert result["target-orders"]["over_threshold"] is True


@pytest.mark.asyncio
async def test_probe_services_once_under_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """p95 of 100ms and error rate 0.0 sets over_threshold to false."""

    async def fake_query(client: httpx.AsyncClient, promql: str) -> dict[str, float]:
        if "histogram_quantile" in promql:
            return {"target-orders": 100.0}
        return {"target-orders": 0.0}

    async def fake_healthz(client: httpx.AsyncClient, url: str) -> bool:
        return True

    monkeypatch.setattr(tools, "query_prometheus", fake_query)
    monkeypatch.setattr(tools, "probe_healthz", fake_healthz)

    async with httpx.AsyncClient() as client:
        result = await tools._probe_services_once(client, ["target-orders"])

    assert result["target-orders"]["metrics"]["p95_latency"] == 100.0
    assert result["target-orders"]["metrics"]["error_rate"] == 0.0
    assert result["target-orders"]["over_threshold"] is False


@pytest.mark.asyncio
async def test_probe_services_once_error_rate_over_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """error rate of 0.5 against 0.10 threshold sets over_threshold to true."""

    async def fake_query(client: httpx.AsyncClient, promql: str) -> dict[str, float]:
        if "histogram_quantile" in promql:
            return {"target-orders": 100.0}
        return {"target-orders": 0.5}

    async def fake_healthz(client: httpx.AsyncClient, url: str) -> bool:
        return True

    monkeypatch.setattr(tools, "query_prometheus", fake_query)
    monkeypatch.setattr(tools, "probe_healthz", fake_healthz)

    async with httpx.AsyncClient() as client:
        result = await tools._probe_services_once(client, ["target-orders"])

    assert result["target-orders"]["metrics"]["error_rate"] == 0.5
    assert result["target-orders"]["over_threshold"] is True
