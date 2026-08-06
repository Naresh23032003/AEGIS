# ADR-002: Executor allowlist and hardened containers instead of gVisor

## Status

Accepted.

## Context

core-executor is the only process with a Docker socket mount, and it runs
actions an LLM agent proposed. It needs strong isolation between "the action
the catalog defines" and "arbitrary code on the host." gVisor (runsc) is the
usual answer for sandboxing untrusted container workloads.

## Decision

Isolate with a closed action catalog (ADR-005), an explicit allowlist in
core-executor, and hardened container settings (no new privileges, dropped
capabilities, read-only root filesystem where the action allows it) instead
of gVisor.

## Consequences

The demo runs unmodified with plain Docker Desktop on macOS and Linux.
gVisor is Linux-only and requires a compatible container runtime
configuration; requiring it would break `docker compose up` on the exact
machine a hiring reviewer is most likely to use. The allowlist plus closed
catalog means the executor never interprets free-form input as a command in
the first place, which is the more relevant boundary for this threat model:
the risk is a manipulated LLM proposing a bad action, not an untrusted binary
escaping its container.
