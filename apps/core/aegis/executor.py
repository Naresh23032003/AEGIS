"""aegis.executor: the only process allowed to touch the Docker socket.

Phase 2: serves aegis.executor_app on internal port 8090 (plan/01, Runtime
topology). Every container operation goes through the docker SDK, never a
shell-invoking subprocess call, per CLAUDE.md and plan/04-security.md,
Executor sandbox.
"""

import uvicorn


def main() -> None:
    uvicorn.run("aegis.executor_app:app", host="0.0.0.0", port=8090, log_level="info")  # noqa: S104


if __name__ == "__main__":
    main()
