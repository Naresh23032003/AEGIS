"""plan/03-agents-and-policy.md, Supervisor: "Unit test with a stubbed hung
node." A hung node is one whose agent_runs row stopped heartbeating; that
row is stubbed here directly rather than actually running a node that
blocks forever, which would make the test slow without exercising any
different code path (the supervisor only ever looks at the row)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from aegis.agents import supervisor as supervisor_mod


class FakeTxn:
    async def __aenter__(self) -> FakeTxn:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeConn:
    def __init__(self, stale_rows: list[dict[str, Any]]) -> None:
        self.stale_rows = stale_rows
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        return self.stale_rows

    async def execute(self, query: str, *args: Any) -> None:
        self.executed.append((query, args))

    def transaction(self) -> FakeTxn:
        return FakeTxn()


class FakeConnCtx:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> FakeConn:
        return self.conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


@pytest.fixture
def stubbed_hung_node(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeConn, list[dict[str, Any]]]:
    stale_row = {"id": "run_1", "incident_id": "inc_1", "agent": "diagnose"}
    conn = FakeConn([stale_row])
    monkeypatch.setattr(supervisor_mod.db, "connection", lambda: FakeConnCtx(conn))

    emitted: list[dict[str, Any]] = []

    async def fake_emit(
        _conn: Any, *, incident_id: str, type: str, actor: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        emitted.append(
            {"incident_id": incident_id, "type": type, "actor": actor, "payload": payload}
        )
        return {}

    monkeypatch.setattr(supervisor_mod, "emit", fake_emit)
    return conn, emitted


async def test_hung_node_is_quarantined_and_resumed_once(
    stubbed_hung_node: tuple[FakeConn, list[dict[str, Any]]],
) -> None:
    conn, emitted = stubbed_hung_node
    resumed: list[str] = []

    async def resume(incident_id: str) -> None:
        resumed.append(incident_id)

    sup = supervisor_mod.Supervisor(resume)
    acted = await sup.watch_once(now=datetime.now(UTC))

    assert acted == ["inc_1"]
    assert resumed == ["inc_1"]
    assert any(e["type"] == "agent.quarantined" for e in emitted)
    assert any("quarantined" in q for q, _ in conn.executed)


async def test_a_second_stall_on_the_same_incident_escalates_without_resuming_again(
    stubbed_hung_node: tuple[FakeConn, list[dict[str, Any]]],
) -> None:
    _conn, emitted = stubbed_hung_node
    resumed: list[str] = []

    async def resume(incident_id: str) -> None:
        resumed.append(incident_id)

    sup = supervisor_mod.Supervisor(resume)
    await sup.watch_once(now=datetime.now(UTC))
    await sup.watch_once(now=datetime.now(UTC))

    assert resumed == ["inc_1"]  # only one resume attempt ever
    assert sum(1 for e in emitted if e["type"] == "incident.escalated") == 1


async def test_a_resume_that_raises_escalates_immediately(
    stubbed_hung_node: tuple[FakeConn, list[dict[str, Any]]],
) -> None:
    _conn, emitted = stubbed_hung_node

    async def resume(incident_id: str) -> None:
        raise RuntimeError("resume boom")

    sup = supervisor_mod.Supervisor(resume)
    await sup.watch_once(now=datetime.now(UTC))

    assert any(e["type"] == "incident.escalated" for e in emitted)
