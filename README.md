# AEGIS

Self-healing incident operations platform. Detects injected faults, diagnoses
them with a team of LLM agents, fixes low risk problems on its own, routes
risky fixes through signed human approval, verifies the result, and replays
every decision in a flight recorder UI.

This repo is being built from the specification in [PLAN.md](PLAN.md) and
[plan/](plan/), one phase at a time. The launch README with the demo GIF,
architecture diagram, and measured MTTR numbers lands in phase 6
([plan/07-review-and-launch.md](plan/07-review-and-launch.md)); until then
this file just tracks where the build stands.

## Status

Phase 0 (skeleton): monorepo layout, contracts codegen, compose stack with
stub services, CI. See [docs/reports/PHASE_0_REPORT.md](docs/reports/PHASE_0_REPORT.md).

## Quickstart (phase 0)

```
cp .env.example .env      # MOCK_LLM=1 by default, no API key needed
make up                   # docker compose up -d --build
```

`core-api` (<http://localhost:8080/healthz>), `console`
(<http://localhost:3000>), and the target services are stubs at this phase;
they only answer health checks. Grafana is at <http://localhost:3001>.

```
make down                 # tear down
make lint test             # ruff + mypy + eslint + prettier + pytest + opa test
```

## Layout

See [plan/01-architecture.md](plan/01-architecture.md) for the full monorepo
layout and locked stack. Summary: `apps/console` (Next.js), `apps/core`
(FastAPI api/worker/executor), `apps/target` (the demo system that gets
broken and healed), `packages/contracts` (JSON Schema source of truth),
`packages/policies` (OPA/Rego), `deploy/` (compose stack).
