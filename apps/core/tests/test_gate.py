"""Unit coverage for gate.py's pure-ish helpers (OPA input construction,
runaway-brake counting, and the veto-window wait's fast paths), stubbing
aegis.db the same way test_supervisor.py does. gate()'s full orchestration
(OPA allow/deny, the real 30s veto wait, and the red-tier LangGraph
interrupt/resume) is covered live instead, by e2e/test_approvals.py: faking
asyncpg well enough to also fake LangGraph's interrupt() checkpointing and
Postgres's own hash-chained emit() would mostly be re-implementing both,
for less confidence than running them for real against the live stack.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from typing import Any

# aegis.agents.nodes' __init__ rebinds the "gate" attribute on the package
# to the gate() function it re-exports (from aegis.agents.nodes.gate import
# gate), which shadows the submodule for a dotted `import ... as` after that
# __init__ has run; sys.modules is the one lookup that always finds the real
# module regardless of import order.
import aegis.agents.nodes.gate  # noqa: F401 - ensures it is loaded into sys.modules
import pytest

gate_mod = sys.modules["aegis.agents.nodes.gate"]


class FakeConn:
    def __init__(self, *, fetchval: Any = None, fetchrow: Any = None) -> None:
        self._fetchval = fetchval
        self._fetchrow = fetchrow

    async def fetchval(self, _query: str, *_args: Any) -> Any:
        return self._fetchval

    async def fetchrow(self, _query: str, *_args: Any) -> Any:
        return self._fetchrow


class FakeConnCtx:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> FakeConn:
        return self.conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _patch_conn(monkeypatch: pytest.MonkeyPatch, conn: FakeConn) -> None:
    monkeypatch.setattr(gate_mod.db, "connection", lambda: FakeConnCtx(conn))


async def test_actions_executed_count_reads_executed_only() -> None:
    conn = FakeConn(fetchval=3)
    assert await gate_mod._actions_executed_count(conn, "inc_1") == 3


async def test_already_scaled_true_when_more_executed_than_rolled_back() -> None:
    conn = FakeConn(fetchrow={"up": 2, "down": 1})
    assert await gate_mod._already_scaled(conn, "inc_1", "target-orders") is True


async def test_already_scaled_false_once_rolled_back_catches_up() -> None:
    conn = FakeConn(fetchrow={"up": 2, "down": 2})
    assert await gate_mod._already_scaled(conn, "inc_1", "target-orders") is False


async def test_already_scaled_false_with_no_service_param() -> None:
    conn = FakeConn()
    assert await gate_mod._already_scaled(conn, "inc_1", None) is False


async def test_wait_for_veto_short_circuits_when_already_vetoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_conn(monkeypatch, FakeConn(fetchval="vetoed"))
    outcome = await gate_mod._wait_for_veto_or_timeout("inc_1", "act_1")
    assert outcome == "vetoed"


async def test_wait_for_veto_denied_action_is_not_a_veto_window_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_conn(monkeypatch, FakeConn(fetchval="denied"))
    outcome = await gate_mod._wait_for_veto_or_timeout("inc_1", "act_1")
    assert outcome == "denied"


async def test_wait_for_veto_returns_executing_once_window_already_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates a crash-restart replay of gate: the window opened, and by
    the time this node re-runs, its closes_at (recomputed from the
    persisted event, not held in memory) is already in the past. Must
    return immediately, with no 30-second sleep."""
    _patch_conn(monkeypatch, FakeConn(fetchval="executing"))
    past = datetime.now(UTC) - timedelta(seconds=5)

    async def fake_closes_at(_incident_id: str, _action_id: str) -> datetime:
        return past

    monkeypatch.setattr(gate_mod.approvals, "veto_closes_at", fake_closes_at)

    outcome = await gate_mod._wait_for_veto_or_timeout("inc_1", "act_1")
    assert outcome == "executing"
