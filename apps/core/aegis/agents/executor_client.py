"""HTTP client for core-executor. plan/04-security.md, Executor sandbox:
core-worker never touches the Docker socket itself; every mutating action
and every container-stats read goes through this one internal RPC client,
authenticated with a shared secret header.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

EXECUTOR_URL = os.environ.get("EXECUTOR_URL", "http://core-executor:8090")
EXECUTOR_SHARED_SECRET = os.environ.get("EXECUTOR_SHARED_SECRET", "")


class ExecutorError(RuntimeError):
    pass


def headers() -> dict[str, str]:
    return {"X-Aegis-Executor-Secret": EXECUTOR_SHARED_SECRET}


async def execute(
    *, action_id: str, incident_id: str, catalog_key: str, params: dict[str, Any]
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{EXECUTOR_URL}/execute",
            headers=headers(),
            json={
                "action_id": action_id,
                "incident_id": incident_id,
                "catalog_key": catalog_key,
                "params": params,
            },
        )
    if resp.status_code != 200:
        raise ExecutorError(f"executor returned {resp.status_code}: {resp.text}")
    result: dict[str, Any] = resp.json()
    return result


async def container_stats(service: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{EXECUTOR_URL}/stats/{service}", headers=headers())
    if resp.status_code != 200:
        raise ExecutorError(f"executor stats {resp.status_code}: {resp.text}")
    result: dict[str, Any] = resp.json()
    return result
