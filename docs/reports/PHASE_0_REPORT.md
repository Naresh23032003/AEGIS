# Phase 0 report: Skeleton

## Built

- Monorepo layout per plan/01-architecture.md: `apps/console`, `apps/core`
  (one Python package, three entrypoints: `aegis.api`, `aegis.worker`,
  `aegis.executor`), `apps/target/{gateway,orders,payments}`, `apps/loadgen`,
  `packages/contracts`, `packages/policies`, `deploy/`, `docs/adr`,
  `docs/reports`, `e2e/` (empty, phase 1+), `design-system/` (empty, phase
  4).
- Tooling: ruff (repo-wide) and mypy strict (`apps/core` only, per
  CLAUDE.md) in root `pyproject.toml`; eslint flat config + prettier for the
  TS side; `tsconfig.base.json` shared by `apps/console` and
  `packages/contracts`.
- `packages/contracts`: JSON Schemas for the event envelope, `IncidentState`,
  and the types it closes over (`Incident`, `Evidence`, `ActionProposal`,
  `VerifyResult`). Codegen wired to `make contracts`:
  `packages/contracts/scripts/gen_python.sh` (datamodel-code-generator ->
  Pydantic v2, `apps/core/aegis/contracts/generated/`, re-exported from
  `aegis/contracts/__init__.py`) and `scripts/gen-ts.mjs`
  (json-schema-to-typescript -> `packages/contracts/generated/ts/index.ts`).
  Verified both import/typecheck cleanly (see output below).
- `deploy/docker-compose.yml`: all 14 services from the plan/01 topology
  table. postgres x2, redis, opa, toxiproxy, lgtm are the real pinned
  images with healthchecks. Target services, core-api/worker/executor,
  console, and loadgen are phase-0 stubs (healthz only, or a heartbeat loop
  for the ones with no HTTP port).
- `Makefile` with every target from plan/06: `up`, `down`, `contracts`
  (+ `-python`/`-ts`), `test` (+ `-python`/`-ts`, `opa-test`), `lint`
  (+ `-python`/`-ts`), `e2e`, `e2e-live`, `record-fixtures`, plus `venv` and
  `env` helpers.
- `.env.example`, `.gitignore`, `.dockerignore`,
  `.github/workflows/ci.yml` (setup-python 3.12 + setup-node 22, installs,
  `make contracts`, `make lint`, `make test`, `make e2e`).
- `docs/adr/ADR-001` through `ADR-008`, one per summary in plan/01.
- Root `README.md` (phase-0-appropriate status page, not the launch README;
  that is phase 6).

## Deviations and choices (spec was silent)

- **Evidence shape.** plan/03 describes evidence only in prose ("log lines,
  metric snapshots, trace summaries, each with source ref"). I defined
  `Evidence { kind: log|metric|trace, source, ref, content }` as the
  simplest shape matching that description. This is not a new event type,
  route, column, or catalog action, but it is a genuine guess; flagging for
  revisit once phase 2's diagnosis tools (`query_logs`, `query_metrics`,
  `query_traces`) produce real output.
- **Target apps and loadgen use `requirements.txt`, not `pyproject.toml`.**
  They are single-file stub scripts run directly in their own container,
  not imported anywhere. `apps/core` is a real installable package (three
  entrypoints share `aegis.*`), so it gets `pyproject.toml` + hatchling.
- **`make lint` runs mypy too**, even though plan/06's one-line summary of
  the target says "ruff + eslint + prettier check." CLAUDE.md separately
  requires "ruff + mypy strict on apps/core," and there is no other target
  for it to live in; folded into `lint-python`.
- **Console is hand-built, not `create-next-app`.** Next 15.5.22 (pinned,
  matches the locked "Next 15.x"), App Router, Tailwind v4. No R3F, xyflow,
  cmdk, motion, or zustand yet; those are phase 4/5 per plan/06.
- **Image pins** (checked against registries at build time, not guessed):
  `postgres:16.14`, `redis:7.4.10`, `openpolicyagent/opa:1.19.0-debug`,
  `ghcr.io/shopify/toxiproxy:2.10.0`, `grafana/otel-lgtm:0.28.0`,
  `python:3.12.13-slim-bookworm`, `node:22.23.2-bookworm-slim`.
- **OPA's plain image has no shell**; used the `-debug` variant (Wolfi
  based) so the healthcheck has something to run. Even that image has no
  `wget`/`curl`, only busybox; the healthcheck confirms port 8181 is
  listening (`netstat -tln | grep :8181`) rather than making an HTTP call.
  That is a liveness check, not a policy-readiness check; real policy
  coverage is opa test in `make test`, which does exercise the API.
- **`grafana/otel-lgtm` has `curl` but not `wget`** (RHEL9 base); the
  healthcheck uses `curl -sf .../api/health`.
- **Next.js standalone server binds to `$HOSTNAME`** if set, and Docker
  auto-sets `$HOSTNAME` to the container id, which resolves to the
  container's own IP, not `127.0.0.1`. The console healthcheck failed
  against `localhost:3000` until `ENV HOSTNAME=0.0.0.0` was added to the
  Dockerfile's run stage. Leaving this note here because it is a silent
  trap: the container runs fine, logs "Ready," and only the loopback health
  probe fails.
- **`scripts/gate.sh`'s em-dash grep** was repo-wide and caught the one
  banned character, quoted literally inside plan/07's own description of
  that same check, as part of a shell one-liner. Excluded `plan/` and
  `PLAN.md` from that grep; they are the pre-existing spec, not writing
  this repo produces, so CLAUDE.md's writing rules do not apply to them and
  I did not edit their content.
- **Git repository boundary.** `apps/`, `docs/`, etc. were sitting inside
  the user's home directory git repo (`.git` at `/Users/naresh`, remote
  `naresh-portfolio`, an unrelated 3-file GitHub Pages site), not a repo of
  their own. Flagged this to the user before touching git rather than
  guessing; they chose to `git init` a fresh, independent repository at
  `/Users/naresh/Documents/AEGIS` and supplied a new empty remote
  (`https://github.com/Naresh23032003/AEGIS.git`) to push to. No AEGIS
  content was ever staged in the home-directory repo.

## Open questions

- npm audit flags 3 high-severity advisories transitively bundled inside
  `next@15.5.22` (its own vendored `postcss` and `sharp`). The only fix npm
  offers is Next 16, which conflicts with plan/01's locked "Next 15.x."
  Leaving pinned at 15.5.22 and flagging rather than silently bumping the
  locked stack; revisit if a 15.x patch lands or if this needs an explicit
  spec update.
- `core-worker`, `core-executor`, and `loadgen` have no HTTP port and so no
  compose healthcheck; they show as "running," not "healthy." Fine for
  phase 0 stubs (heartbeat log line every 10s). Once they carry real work in
  phase 1/2, worth deciding whether a heartbeat-based liveness signal should
  feed a healthcheck.

## Verification output

`make up` from a torn-down state (`make down` immediately prior), timed:

```
$ time make up
...
 Container aegis-console-1  Starting
 Container aegis-console-1  Started
make up  0.85s user 0.53s system 9% cpu 15.293 total
```

All 14 containers healthy (or running, for the three with no HTTP port),
measured continuously from the same `make up` above, no manual restarts:

```
$ docker compose -f deploy/docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}"
NAME                      STATUS
aegis-aegis-db-1          Up 17 seconds (healthy)
aegis-console-1           Up 6 seconds (healthy)
aegis-core-api-1          Up 11 seconds (healthy)
aegis-core-executor-1     Up 12 seconds
aegis-core-worker-1       Up 12 seconds
aegis-lgtm-1              Up 17 seconds (healthy)
aegis-loadgen-1           Up 11 seconds
aegis-opa-1               Up 17 seconds (healthy)
aegis-redis-1             Up 17 seconds (healthy)
aegis-shop-db-1           Up 17 seconds (healthy)
aegis-target-gateway-1    Up 17 seconds (healthy)
aegis-target-orders-1     Up 12 seconds (healthy)
aegis-target-payments-1   Up 17 seconds (healthy)
aegis-toxiproxy-1         Up 17 seconds (healthy)
```

15s to bring the stack up, fully healthy within 17s more: 32s total,
against the 5 minute budget. (This run had layer/pip/npm caches warm from
an earlier build in the same session; the first ever build, with cold
caches, still completed and reached the same all-healthy state in under 3
minutes.)

`make lint`:

```
$ make lint
.venv/bin/ruff check .
All checks passed!
.venv/bin/mypy
Success: no issues found in 12 source files
npm run lint
> @aegis/console@0.1.0 lint / eslint .
> @aegis/contracts@0.1.0 lint / eslint .
npm run format:check
> prettier --check .
Checking formatting...
All matched files use Prettier code style!
```

`make test`:

```
$ make test
.venv/bin/python -m pytest apps/core -q
...                                                                      [100%]
3 passed, 1 warning in 0.18s
npx -w @aegis/console tsc --noEmit
npx -w @aegis/contracts tsc --noEmit
.bin/opa test packages/policies -v
packages/policies/aegis_test.rego:5:
data.aegis.test_default_deny: PASS (684.917µs)
--------------------------------------------------------------------------------
PASS: 1/1
```

`make e2e` (no scenarios exist before phase 1, exits 0 by design):

```
$ make e2e
no e2e tests yet (phase 0)
```

Contracts round trip, both languages import/typecheck cleanly:

```
$ .venv/bin/python -c "from aegis.contracts import EventEnvelope, IncidentState, ActionProposal, Incident, Evidence, VerifyResult, Tier, Kind, Severity, Status, Autonomy; print('import ok')"
import ok
$ npx -w @aegis/contracts tsc --noEmit
(no output, exit 0)
```

## Next

Stop here for review. Phase 1 (target system, telemetry, detection) starts
a new session per PLAN.md's rule against reading ahead.
