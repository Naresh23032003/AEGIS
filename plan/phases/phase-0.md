# Phase 0 brief: Skeleton

Goal: a repo where every later phase only fills in code. Compose stack boots, CI is green, contracts codegen works, ADRs exist.

## Read (in this order, nothing else)

1. CLAUDE.md (repo root)
2. This file
3. plan/06-milestones.md, "Phase 0" section and the global Makefile targets block
4. plan/01-architecture.md, all of it (this is the one phase that needs the whole architecture file)
5. plan/02-contracts.md, sections "Event envelope" and the IncidentState/ActionProposal mentions in plan/03 "Agent graph" (schemas only, skip the rest)

## Build order

1. Directory tree and package manifests exactly as plan/01. Tooling configs: ruff, mypy strict (apps/core), eslint, prettier, tsconfig.
2. packages/contracts: JSON Schemas for the event envelope, IncidentState, ActionProposal, plus codegen scripts wired to `make contracts`. Verify a generated Pydantic model and TS type both import cleanly.
3. deploy/docker-compose.yml with all services from the plan/01 table. Target services may be stub FastAPI apps returning healthz. Postgres (both), redis, opa, toxiproxy, lgtm must be the real images with healthchecks.
4. Makefile with all global targets (e2e targets may exit 0 with "no tests yet").
5. .env.example, .gitignore, GitHub Actions workflow: lint + test + opa test on push.
6. docs/adr/ADR-001..008 from the summaries at the bottom of plan/01, each under a page.

## Gotchas

- Pin image tags in compose; latest breaks demos.
- lgtm container needs 4317/4318 exposed on the compose network only, Grafana on host 3001.
- OPA starts with packages/policies mounted even though policies arrive in phase 3; an empty package that returns default deny is fine and gets replaced.

## Exit ritual (same every phase)

Run the phase's acceptance checks from plan/06. Write docs/reports/PHASE_0_REPORT.md (built, deviations, pasted command output, open questions). Commit conventionally, branch phase-0, tag phase-0, push. Stop. Do not read ahead or start phase 1.
