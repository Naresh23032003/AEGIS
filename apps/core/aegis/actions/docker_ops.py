"""Docker SDK calls. Imported only by aegis.executor_app: core-executor is
the one process with the Docker socket mounted (plan/04-security.md,
Executor sandbox). Every call goes through the docker SDK directly, never
a shell-invoking subprocess or an interpolated command string.
"""

from __future__ import annotations

from typing import Any

import docker
from docker.errors import NotFound


def _client() -> docker.DockerClient:
    return docker.from_env()


def restart_container(name: str) -> dict[str, Any]:
    _client().containers.get(name).restart(timeout=5)
    return {"container": name, "action": "restart"}


def stop_container(name: str) -> dict[str, Any]:
    _client().containers.get(name).stop(timeout=5)
    return {"container": name, "action": "stop"}


def start_container(name: str) -> dict[str, Any]:
    container = _client().containers.get(name)
    if container.status != "running":
        container.start()
    return {"container": name, "action": "start"}


def pause_container(name: str) -> dict[str, Any]:
    container = _client().containers.get(name)
    if container.status != "paused":
        container.pause()
    return {"container": name, "action": "pause"}


def unpause_container(name: str) -> dict[str, Any]:
    container = _client().containers.get(name)
    if container.status == "paused":
        container.unpause()
    return {"container": name, "action": "unpause"}


def container_stats(name: str) -> dict[str, Any]:
    try:
        container = _client().containers.get(name)
    except NotFound:
        return {"container": name, "status": "not_found"}
    raw = container.stats(stream=False)
    if not isinstance(raw, dict):
        # stream=False always returns a single dict at runtime; the docker
        # SDK's stub types the overload loosely on the stream flag's type,
        # not its value.
        raise TypeError(f"unexpected stats() result for {name}: {type(raw)}")
    cpu_delta = (
        raw["cpu_stats"]["cpu_usage"]["total_usage"]
        - raw["precpu_stats"]["cpu_usage"]["total_usage"]
    )
    system_delta = raw["cpu_stats"].get("system_cpu_usage", 0) - raw["precpu_stats"].get(
        "system_cpu_usage", 0
    )
    cpu_percent = 0.0
    if system_delta > 0 and cpu_delta > 0:
        online_cpus = raw["cpu_stats"].get("online_cpus") or 1
        cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100, 2)
    mem_usage = raw.get("memory_stats", {}).get("usage", 0)
    mem_limit = raw.get("memory_stats", {}).get("limit", 0)
    return {
        "container": name,
        "status": container.status,
        "cpu_percent": cpu_percent,
        "memory_usage_bytes": mem_usage,
        "memory_limit_bytes": mem_limit,
    }
