"""aegis.policy: the OPA HTTP client. Stubs httpx.AsyncClient (same pattern
as test_supervisor.py's FakeConn) rather than requiring a running OPA
server for `make test`; packages/policies' own rules are covered by
`opa test` (Makefile's opa-test target), not here."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from aegis import policy


class FakeResponse:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict[str, Any]:
        return self._body


class FakeAsyncClient:
    def __init__(self, response: FakeResponse | Exception, captured: list[dict[str, Any]]) -> None:
        self._response = response
        self._captured = captured

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
        self._captured.append({"url": url, "json": json})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _patch_client(
    monkeypatch: pytest.MonkeyPatch, response: FakeResponse | Exception
) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        policy.httpx, "AsyncClient", lambda **_kw: FakeAsyncClient(response, captured)
    )
    return captured


def _action(confidence: float = 0.9) -> dict[str, Any]:
    return {
        "catalog_key": "restart_service",
        "params": {},
        "tier": "green",
        "confidence": confidence,
    }


_INCIDENT = {"severity": "sev2", "loop_count": 0, "actions_executed": 0}
_CONTEXT = {"env": "demo"}


async def test_evaluate_returns_allow_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_client(
        monkeypatch,
        FakeResponse({"result": {"allow": True, "rule_id": "allow_green_tier", "reason": "ok"}}),
    )

    decision = await policy.evaluate(action=_action(), incident=_INCIDENT, context=_CONTEXT)

    assert decision.allow is True
    assert decision.rule_id == "allow_green_tier"
    assert captured[0]["json"]["input"]["action"]["catalog_key"] == "restart_service"


async def test_evaluate_returns_deny_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        FakeResponse(
            {"result": {"allow": False, "rule_id": "deny_low_confidence", "reason": "no"}}
        ),
    )

    decision = await policy.evaluate(
        action=_action(confidence=0.1), incident=_INCIDENT, context=_CONTEXT
    )

    assert decision.allow is False
    assert decision.rule_id == "deny_low_confidence"


async def test_evaluate_raises_policy_error_on_unreachable_opa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, httpx.ConnectError("connection refused"))

    with pytest.raises(policy.PolicyError):
        await policy.evaluate(action=_action(), incident=_INCIDENT, context=_CONTEXT)


async def test_evaluate_raises_policy_error_on_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, FakeResponse({"result": {"allow": True}}))  # missing rule_id

    with pytest.raises(policy.PolicyError):
        await policy.evaluate(action=_action(), incident=_INCIDENT, context=_CONTEXT)
