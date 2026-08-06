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


def container_state(name: str) -> dict[str, Any]:
    """Inspect-only state (status, OOM flag, exit code), no live stats call.
    plan/phases/phase-2.md's open question (PHASE_2_REPORT.md): service_down
    fires for both crash (docker stop) and memory_leak (OOM kill) on the
    same container; OOMKilled is the one signal that tells them apart
    without adding a second detection rule (see aegis.agents.state)."""
    try:
        container = _client().containers.get(name)
    except NotFound:
        return {"container": name, "status": "not_found", "oom_killed": False, "exit_code": None}
    state = container.attrs.get("State", {})
    return {
        "container": name,
        "status": container.status,
        "oom_killed": bool(state.get("OOMKilled", False)),
        "exit_code": state.get("ExitCode"),
    }


def clone_and_start(name: str, clone_name: str) -> dict[str, Any]:
    """scale_service's "1 -> 2": start a second container from the same
    image/env/network as `name`, published on no host ports (the original
    already owns those). Docker Compose's own scaling is a CLI concept
    (`docker compose up --scale`), not a docker-SDK primitive, and the
    executor never shells out (plan/04-security.md); cloning the running
    container's own config through the SDK gets the same effect without a
    subprocess. Idempotent: a pre-existing clone is left running as-is."""
    client = _client()
    try:
        existing = client.containers.get(clone_name)
    except NotFound:
        pass
    else:
        if existing.status != "running":
            existing.start()
        return {"container": clone_name, "action": "scale_up", "already_existed": True}

    source = client.containers.get(name)
    networks = list(source.attrs["NetworkSettings"]["Networks"])
    image_id = source.attrs["Image"]
    client.containers.run(
        image_id,
        name=clone_name,
        environment=source.attrs["Config"].get("Env", []),
        network=networks[0] if networks else None,
        detach=True,
    )
    return {"container": clone_name, "action": "scale_up", "already_existed": False}


def stop_and_remove(clone_name: str) -> dict[str, Any]:
    """scale_service's rollback ("scale back to 1"): stop and remove the
    clone created by clone_and_start. A clone that never existed is a
    no-op, not an error (rollback of an action that never ran)."""
    try:
        container = _client().containers.get(clone_name)
    except NotFound:
        return {"container": clone_name, "action": "scale_down", "existed": False}
    container.stop(timeout=5)
    container.remove()
    return {"container": clone_name, "action": "scale_down", "existed": True}


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
