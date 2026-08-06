"""plan/06-milestones.md, Phase 2 acceptance: "killing core-worker mid-run
and restarting resumes the run from checkpoint." Found live investigating
the phase 3/4 CI failure: Runner.resume_orphaned_runs used to spawn
self.resume(incident_id) instead of resume_incident(...) directly, and
spawn() marks an incident in_flight *before* its task body runs -- so
self.resume's own in_flight check always saw the entry spawn() had just
added for it and returned immediately, never calling resume_incident.
Every orphaned run silently no-op'd at startup, permanently stuck in
'resolving'. This is a pure unit test of that dispatch wiring: it stubs
resume_incident and asserts resume_orphaned_runs actually reaches it,
which is the one thing the previous code never did."""

from __future__ import annotations

import asyncio
from typing import Any

from aegis import worker as worker_mod


class FakeConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        return self.rows


class FakeConnCtx:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> FakeConn:
        return self.conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


async def test_resume_orphaned_runs_actually_calls_resume_incident(
    monkeypatch: Any,
) -> None:
    rows = [{"id": "inc_orphan_1"}, {"id": "inc_orphan_2"}]
    monkeypatch.setattr(worker_mod.db, "connection", lambda: FakeConnCtx(FakeConn(rows)))

    resumed: list[str] = []

    async def fake_resume_incident(graph: Any, *, incident_id: str) -> None:
        resumed.append(incident_id)

    monkeypatch.setattr(worker_mod, "resume_incident", fake_resume_incident)

    runner = worker_mod.Runner(graph=object())
    await runner.resume_orphaned_runs()
    # spawn() only schedules the tasks; wait for them to actually run.
    await asyncio.gather(*runner.tasks)

    assert sorted(resumed) == ["inc_orphan_1", "inc_orphan_2"]
    # Neither task should be left dangling once it has run.
    assert runner.in_flight == set()


async def test_resume_orphaned_runs_does_not_self_block_via_in_flight(
    monkeypatch: Any,
) -> None:
    """The specific failure mode: if resume_orphaned_runs routed through
    Runner.resume() again, this would assert 0 calls instead of 1, since
    resume()'s own in_flight guard would see the entry spawn() just added
    and skip."""
    rows = [{"id": "inc_orphan_1"}]
    monkeypatch.setattr(worker_mod.db, "connection", lambda: FakeConnCtx(FakeConn(rows)))

    calls = 0

    async def fake_resume_incident(graph: Any, *, incident_id: str) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(worker_mod, "resume_incident", fake_resume_incident)

    runner = worker_mod.Runner(graph=object())
    await runner.resume_orphaned_runs()
    await asyncio.gather(*runner.tasks)

    assert calls == 1
