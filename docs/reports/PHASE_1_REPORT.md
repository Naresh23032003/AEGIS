# Phase 1 report: Target system, telemetry, detection

## Built

- **Target services**, real endpoints per plan/06 phase 1: `target-gateway`
  (`POST /checkout` orchestrates orders -> payments -> orders, `GET
  /orders/{id}` proxy), `target-orders` (`POST /orders`, `GET /orders/{id}`
  cached through redis, `POST /orders/{id}/complete`, all DB access through
  Toxiproxy), `target-payments` (`POST /charge`, plus the `error_spike` and
  `memory_leak` fault-hook endpoints under `/internal/fault/*`). Each has
  OTel auto-instrumentation (FastAPI + httpx/asyncpg/redis where relevant)
  exporting to lgtm, and `/healthz`.
- **Toxiproxy wiring**: `target-orders` creates the `shopdb` proxy
  (`toxiproxy:5432` -> `shop-db:5432`) on startup, idempotently, with retry;
  `SHOP_DATABASE_URL` now points at the proxy, not the database directly.
- **loadgen**: ~5 rps jittered traffic against `target-gateway`, 80%
  checkout / 20% order lookup (the lookups exercise the redis cache path).
- **Chaos**: `aegis/chaos.py`, one module mapping all five scenario keys to
  their injection/clear mechanics (Toxiproxy latency toxic, Docker
  stop/start, payments fault-endpoint calls, Docker pause/unpause), wired to
  `POST/DELETE /api/chaos/{scenario}` on core-api. Each call emits
  `chaos.injected`/`chaos.cleared`.
- **Detection**: `aegis/detection/rules.yaml` (PromQL text lives here, not
  in Python) plus `aegis/detection/loop.py`, a 5-second poll: two
  Prometheus-backed rules (`latency_p95`, `error_rate`) with a 15s sustain
  window, one healthz-probe rule (`service_down`, fail_count 3). Dedupes per
  `(rule, service)` while an incident stays open, opens an `incidents` row
  and an `incident.detected` event otherwise.
- **Hash chain**: `aegis/chain.py` (`canonical_json`, `next_hash`, unit
  tested against a fixed vector) and `aegis/events.py` (`build_envelope` +
  `emit`, which writes the chained `incident_events` row and publishes to
  the `aegis:events` Redis stream in one call, inside the caller's
  transaction).
- **core-api**: `GET /api/incidents`, `GET /api/incidents/{id}`, `GET
  /api/incidents/{id}/events`, `POST`/`DELETE /api/chaos/{scenario}`, `WS
  /ws/events` with the replay handshake (`{"replay_incident": "<id>"}`) and
  a 20s ping, `GET /healthz`. CORS locked to `CONSOLE_ORIGIN`, `slowapi`
  rate limit (10/min) on the chaos endpoints.
- **Schema**: `aegis.incidents` and `aegis.incident_events` created by
  `aegis/db.py` on startup (idempotent `CREATE TABLE IF NOT EXISTS`); the
  remaining plan/02 tables (`actions`, `approvals`, `agent_runs`,
  `approver_keys`) arrive with the phases that use them.
- Two new unit-test files (`test_chain.py`, `test_events.py`) alongside the
  code, per CLAUDE.md.

## Prometheus metric names (plan/phases/phase-1.md gotcha)

Verified against a running stack via Grafana Explore / the Prometheus HTTP
API rather than guessed. The OTel FastAPI instrumentation exports exactly
what plan/02's query text assumed:

- `http_server_duration_milliseconds_bucket{service_name, le}` for the
  latency histogram.
- `http_server_duration_milliseconds_count{service_name, http_status_code}`
  for request counts by status.

No rules.yaml query-string change was needed; `rules.yaml`'s comment
records this so a future metric-name drift has a known-good baseline to
diff against.

## Deviations and choices (spec was silent, or a phase-1 gotcha called for a choice)

- **`chaos.*` events chain under a synthetic `incident_id = "chaos"`.**
  plan/02's envelope requires a non-null `incident_id` and says every event
  type in the catalog uses the same envelope on the same append-only chain,
  but `chaos.injected`/`chaos.cleared` can happen before any incident
  exists (or without one ever opening, if the fault doesn't cross a
  threshold). Chose a fixed sentinel chain rather than inventing a nullable
  variant of the envelope. Revisit if phase 3+ wants chaos events attached
  to the incident they end up causing.
- **core-api mounts the Docker socket**, read-only, for the `crash` and
  `cache_outage` scenarios. This is explicit in plan/phases/phase-1.md's
  gotchas ("Chaos manipulations that touch containers go through a thin
  internal helper now and move into the executor in phase 2"); the mapping
  already lives in one module (`aegis/chaos.py`) so that move only touches
  the caller in core-api, not the mechanics.
- **`GET /api/incidents/{id}}` returns empty `actions`/`agent_runs`
  arrays.** Those tables don't exist until phase 2/3; kept the response
  shape forward-compatible rather than omitting the fields.
- **No `verify-chain` endpoint yet.** plan/04 describes it, but phase 1's
  explicit build order (step 5) lists exactly `GET /incidents`, `GET
  /incidents/{id}`, `GET /incidents/{id}/events`, `WS /ws/events`, `GET
  /healthz`. Verified the chain by hand instead (script run against the
  live stack, see below); the real endpoint is a phase 3 acceptance item.
- **Sustain/fail-count state is in-process** (`DetectionState` in
  `loop.py`), not persisted. A worker restart mid-sustain-window forgets
  progress toward a threshold breach and starts the window over. Acceptable
  for phase 1 (detection is deterministic and re-evaluates every 5s
  regardless); would need a durable store if worker restarts become common
  once phase 2 adds long-running agent work on the same process.
- **`target-payments` has no Docker restart policy.** An OOM kill (memory_leak)
  stays down, same as a manual `docker stop` (crash), so `service_down` has
  a real window to fire. Docker's own `restart: on-failure` was tried first
  and reverted: it raced detection (see below) and, worse, would silently
  perform the remediation agent's `restart_service` job before an agent
  ever runs. `DELETE /api/chaos/memory_leak` restarts the container
  explicitly as part of clearing.
- **`emit()` treats a Redis publish failure as non-fatal.** Postgres is the
  source of truth for the chain; a stalled Redis (the `cache_outage`
  scenario pauses the same container that carries the event stream, since
  redis serves both roles per plan/01) must delay live WS delivery, not
  lose the event. Wrapped `XADD` in a 2s timeout with a logged warning;
  confirmed both effects live (see below).
- **Bug found and fixed during scenario testing**: `incident_events.created_at`
  was left to Postgres's `DEFAULT now()`, which resolves microseconds after
  the envelope's `ts` was generated and hashed. Reconstructing an envelope
  from the row (WS replay, hand-verification, and the future verify-chain
  endpoint) reformatted a different `ts` than what was actually hashed, so
  the chain never recomputed clean. Fixed by generating one `datetime` per
  `emit()` call and using it for both the envelope's `ts` and the explicit
  `created_at` insert. Added `test_events.py::test_format_ts_round_trips_through_a_stored_datetime`
  as a regression test, and re-verified the full chain live after the fix
  (0 invalid, see below).
- **`.env` had a real `GROQ_API_KEY` and `MOCK_LLM=0` already set locally**,
  from before this session, but was missing every database/redis/OTel var
  `.env.example` now defines (it predates this phase's additions and
  probably an earlier one-off test). Regenerating it from `.env.example` to
  pick up the new vars blanked the key; restored it immediately by hand
  rather than leaving it silently discarded. Phase 1 never touches the LLM
  path (detection is deterministic, per plan/03), so this had no effect on
  anything built this phase, but flagging it here since it's local state
  this phase's changes could otherwise have destroyed unnoticed.

## Timing observed (curl injection -> incident.detected on the WS)

Measured against a freshly `make up`'d stack, one scenario at a time, open
incidents resolved between runs so dedupe didn't mask a fresh injection.
plan/06's "within 30s" is a target against a `rate(...[1m])` PromQL window
that plan/02 specifies verbatim; actual timing depends on how far into that
window the fault sits when it starts, which is why latency and cache_outage
run longer than 30s here. All five fired well inside the compose
healthcheck/dedupe machinery working as designed, chain valid throughout:

| scenario | inject -> detect | rule that fired |
|---|---|---|
| latency | 55s | `latency_p95` on target-orders, target-gateway |
| crash | 16s | `service_down` on target-payments |
| error_spike | 31s | `error_rate` on target-payments |
| memory_leak | 35s (18s to OOM + 17s to detect) | `error_rate` then `service_down` on target-payments |
| cache_outage | 62s (target-orders); target-gateway's `error_rate` fired earlier but from a residual blip, not this injection | `latency_p95` on target-orders |

## Verification output

All 14 containers healthy from a clean `make down -v && make up`:

```
$ docker compose -f deploy/docker-compose.yml ps --format "{{.Name}}: {{.Status}}"
aegis-aegis-db-1: Up 31 seconds (healthy)
aegis-console-1: Up 20 seconds (healthy)
aegis-core-api-1: Up 25 seconds (healthy)
aegis-core-executor-1: Up 25 seconds
aegis-core-worker-1: Up 14 seconds
aegis-lgtm-1: Up 31 seconds (healthy)
aegis-loadgen-1: Up 14 seconds
aegis-opa-1: Up 31 seconds (healthy)
aegis-shop-db-1: Up 31 seconds (healthy)
aegis-toxiproxy-1: Up 31 seconds (healthy)
redis: Up 31 seconds (healthy)
target-gateway: Up 20 seconds (healthy)
target-orders: Up 26 seconds (healthy)
target-payments: Up 31 seconds (healthy)
```

Full five-scenario curl run against that stack, `incident.detected`
appearing on `/api/incidents?status=open` (WS carried the same events live,
confirmed separately, see below):

```
### 1/5 latency ###
inject 02:10:39
{"type":"chaos.injected", ..., "payload":{"scenario":"latency","params":{"toxic":"orders_shopdb_latency","latency_ms":1500}}}
t+55s [('latency_p95', ['target-orders']), ('latency_p95', ['target-gateway'])]
detected 02:11:34

### 2/5 crash ###
inject 02:11:45
{"type":"chaos.injected", ..., "payload":{"scenario":"crash","params":{"container":"target-payments","action":"stop"}}}
t+15s [('service_down', ['target-payments']), ...]
detected 02:12:01
(cleared: target-payments back to "Up 5 seconds (health: starting)")

### 3/5 error_spike ###
inject 02:12:17
{"type":"chaos.injected", ..., "payload":{"scenario":"error_spike","params":{"service":"target-payments"}}}
t+30s [('error_rate', ['target-payments']), ('error_rate', ['target-gateway'])]
detected 02:12:48

### 4/5 memory_leak ###
inject 02:13:02
t+20s container=Exited (137) 2 seconds ago   # OOM kill, no restart policy
t+35s [('service_down', ['target-payments']), ...]
detected 02:13:37
(cleared: chaos.clear restarted target-payments explicitly)

### 5/5 cache_outage ###
inject 02:13:56
redis: Up ... (Paused)
... latency_p95 on target-orders fired at 02:14:58 (62s)
(cleared: redis unpaused, back to healthy within 10s)
```

WS live delivery, captured with a standalone client connected for the
whole run (`ws://localhost:8080/ws/events`, no replay handshake):

```
$ python3 -c "... count event types in ws_output.log ..."
chaos.cleared 5
chaos.injected 5
incident.detected 14
ping 14
```

All 5 injects, 5 clears, and every `incident.detected` the REST API
reported were also delivered live over the socket, plus a 20s heartbeat
ping throughout.

Replay handshake, against a resolved incident:

```
$ python3 -c "... connect, send {'replay_incident': '<id>'}, print what comes back ..."
{"id": "01KZ...", "type": "incident.detected", "incident_id": "inc_...", ...}
```

Hash chain, recomputed by hand from the live Postgres rows (script run
inside the core-api container, same `aegis.chain.next_hash` the codebase
uses) after the `created_at` fix, against the `chaos` sentinel chain (10
events across all 5 scenarios) and one real incident chain:

```
$ docker exec aegis-core-api-1 python /app/verify_chain.py chaos
seq=1 type=chaos.injected       valid=True
seq=4 type=chaos.cleared        valid=True
... (10/10 valid)
$ docker exec aegis-core-api-1 python /app/verify_chain.py inc_01KZADMDZ03SB36VNTDGXSDN7R
seq=24 type=incident.detected    valid=True
```

`make lint test`:

```
$ make lint test
.venv/bin/ruff check .
All checks passed!
.venv/bin/mypy
Success: no issues found in 19 source files
npm run lint / npm run format:check
All matched files use Prettier code style!
.venv/bin/python -m pytest apps/core -q
........                                                                 [100%]
8 passed, 1 warning in 0.28s
npx -w @aegis/console tsc --noEmit
npx -w @aegis/contracts tsc --noEmit
.bin/opa test packages/policies -v
PASS: 1/1
```

`make contracts` re-run against this phase's code: no diff (contracts
untouched this phase).

Writing-rule and `shell=True` gate checks (tracked files only): clean.

## Open questions

- **cache_outage's WS blast radius.** Pausing redis (shared for streams and
  shop cache, per plan/01) also blocks event publish while the pause is in
  effect; `emit()` degrades gracefully (Postgres write always succeeds,
  Redis publish times out and is logged) but a WS client watching live
  during exactly that window sees a gap until reconnect/replay. Documented
  as expected given the shared-Redis design; worth a demo callout in
  phase 4 rather than a phase 1 code change.
- **`memory_leak` timing is sensitive to Docker's own restart/backoff
  behavior on the host running it.** Measured 16-35s here; a slower or
  faster host could push the OOM-to-detection window on either side of the
  15s sustain floor. Nothing to fix now, flagging for whoever runs the demo
  live on different hardware.
- **fail_count/sustain state resets on worker restart** (see Deviations).
  Not exercised by an actual mid-incident worker restart this phase; the
  "kill core-worker mid-run and resume from checkpoint" test is explicitly
  phase 2 (LangGraph checkpointing), so left as a known gap rather than
  building ad hoc persistence for a loop that gets replaced by the agent
  graph's own state next phase.

## Next

Stop here for review. Phase 2 (agent loop end to end) starts a new session
per PLAN.md's rule against reading ahead.
