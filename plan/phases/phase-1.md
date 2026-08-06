# Phase 1 brief: Target system, telemetry, detection

Goal: a believable little production system emitting real telemetry, five working fault injections, and deterministic detection that writes hash-chained incidents and streams events.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. plan/06-milestones.md, "Phase 1" section
4. plan/01-architecture.md, "Runtime topology" table and the numbered data flow (steps 1-3 and 7)
5. plan/02-contracts.md, all of it (you are implementing the envelope, chain, stream, APIs, WS, and detection queries)
6. plan/03-agents-and-policy.md, "Detection" and "Chaos scenarios" sections only
7. plan/04-security.md, "Hash-chained audit log" and "Secrets and transport" sections only

Do not read the agent, policy, or frontend material. It is not needed yet.

## Build order

1. Target services (gateway, orders, payments): small FastAPI apps with the endpoints described in plan/06 phase 1, OTel auto-instrumentation to lgtm, healthz each. Orders reaches shop-db only through Toxiproxy.
2. loadgen container, ~5 rps mixed traffic, jittered.
3. Chaos endpoints in core-api for all five scenarios (inject + clear), each emitting chaos.injected / chaos.cleared. Fault hooks inside payments (error_spike flag file, memory_leak endpoint) and the docker/toxiproxy manipulations for the rest. Chaos manipulations that touch containers go through a thin internal helper now and move into the executor in phase 2; keep the command mapping in one module to make that move trivial.
4. Detection loop in core-worker: rules.yaml, Prometheus queries from plan/02, dedupe per (rule, service), incident row + chained incident_events writes + XADD to aegis:events.
5. core-api: GET /incidents, GET /incidents/{id}, GET /incidents/{id}/events, WS /ws/events with the replay handshake, GET /healthz.

## Gotchas

- Canonical JSON for hashing: sorted keys, separators without spaces, UTF-8. Write the helper once in aegis and unit test it against a fixed vector.
- OTel metric names in the Prometheus queries must match what the FastAPI instrumentation actually exports; verify in Grafana explore before wiring thresholds, and adjust rules.yaml query strings if the exported names differ (record the final names in the phase report).
- memory_leak needs a container memory limit or it will eat the host.
- Detection must keep working while an incident is open (it becomes verification later); dedupe, do not pause.

## Exit ritual

As phase 0: acceptance from plan/06 phase 1, PHASE_1_REPORT.md with pasted curl and WS output, branch/tag phase-1, push, stop.
