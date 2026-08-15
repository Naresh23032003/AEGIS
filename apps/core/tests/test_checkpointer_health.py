"""Defect 17: the worker's LangGraph Postgres checkpointer held a single
connection with no reconnect path, so one dropped connection ended every
later run in `psycopg.OperationalError: the connection is closed` while
the process stayed up and kept claiming incidents.

Two halves are tested here, both without a database: the bounded retry in
aegis.agents.graph._invoke, and the health loop that stops the worker
reporting healthy when the checkpointer cannot answer. The pool half (a
dead connection actually being replaced) needs a real Postgres and lives
in e2e/test_checkpointer_reconnect.py.
"""

from __future__ import annotations

import asyncio
from typing import Any

import psycopg
import pytest
from aegis import worker as worker_mod
from aegis.agents import graph as graph_mod


class FakeGraph:
    """Records what each ainvoke was given, and raises whatever the
    caller queued for that call."""

    def __init__(self, raises: list[Exception | None]) -> None:
        self.raises = raises
        self.inputs: list[Any] = []

    async def ainvoke(self, payload: Any, config: dict[str, Any]) -> None:
        self.inputs.append(payload)
        exc = self.raises[len(self.inputs) - 1]
        if exc is not None:
            raise exc


async def test_invoke_retries_once_from_checkpoint_on_a_dropped_connection() -> None:
    graph = FakeGraph([psycopg.OperationalError("the connection is closed"), None])

    await graph_mod._invoke(graph, "inc_1", {"incident": {}}, None)

    # Second attempt passes None: resume from the last persisted
    # checkpoint rather than restarting the run from the top.
    assert graph.inputs == [{"incident": {}}, None]


async def test_invoke_gives_up_after_one_retry() -> None:
    graph = FakeGraph(
        [
            psycopg.OperationalError("the connection is closed"),
            psycopg.OperationalError("the connection is closed"),
        ]
    )

    with pytest.raises(psycopg.OperationalError):
        await graph_mod._invoke(graph, "inc_1", None, None)

    assert len(graph.inputs) == 2


async def test_invoke_does_not_retry_other_failures() -> None:
    """A model or policy failure is not a connection problem, and retrying
    it would run the incident's remediation a second time."""
    graph = FakeGraph([RuntimeError("diagnose failed schema validation")])

    with pytest.raises(RuntimeError):
        await graph_mod._invoke(graph, "inc_1", None, None)

    assert len(graph.inputs) == 1


async def _run_one_health_pass(monkeypatch: Any, probe: Any) -> asyncio.Event:
    stop = asyncio.Event()

    async def one_pass(checkpointer: Any) -> None:
        try:
            await probe(checkpointer)
        finally:
            stop.set()

    monkeypatch.setattr(worker_mod, "probe_checkpointer", one_pass)
    await worker_mod.run_health_loop(object(), stop)  # type: ignore[arg-type]
    return stop


async def test_worker_reports_healthy_after_the_checkpointer_answers(
    monkeypatch: Any, tmp_path: Any
) -> None:
    monkeypatch.setattr(worker_mod, "HEALTH_FILE", tmp_path / "health")
    assert worker_mod.health_is_fresh() is False

    async def ok(checkpointer: Any) -> None:
        return None

    await _run_one_health_pass(monkeypatch, ok)

    assert worker_mod.health_is_fresh() is True


async def test_worker_reports_unhealthy_while_the_checkpointer_is_dead(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """The whole point of defect 17: a worker that cannot checkpoint must
    not pass its healthcheck. A failed probe writes nothing, so the marker
    ages past HEALTH_STALE_SECONDS and the container turns unhealthy."""
    health_file = tmp_path / "health"
    monkeypatch.setattr(worker_mod, "HEALTH_FILE", health_file)
    stale = 1000.0
    health_file.write_text(f"{stale}\n")

    async def dead(checkpointer: Any) -> None:
        raise psycopg.OperationalError("the connection is closed")

    await _run_one_health_pass(monkeypatch, dead)

    assert health_file.read_text().strip() == "1000.0"
    assert worker_mod.health_is_fresh(now=stale + worker_mod.HEALTH_STALE_SECONDS + 1) is False
    # And it does come back once the pool hands out a live connection.
    assert worker_mod.health_is_fresh(now=stale + 1) is True
