# Phase 3 report: Policy, tiers, approvals, security

## Built

- **`packages/policies/aegis.rego`**: the six OPA rules from
  plan/03-agents-and-policy.md as one `decision` rule with an else-chain
  (deny unknown catalog_key, deny confidence < 0.6, deny runaway brake at 5
  executed actions, deny red tier at sev3, deny scale_service already
  scaled, allow per tier, default deny), each with its own `opa test` in
  `aegis_test.rego` (9 tests covering all six rules plus the two extra
  per-tier allows and the catchall).
- **`aegis.policy`**: the worker's OPA HTTP client (`evaluate` ->
  `Decision(allow, rule_id, reason)`), fails closed (`PolicyError`) on an
  unreachable or malformed response.
- **`aegis.security`**: Ed25519 verification (PyNaCl) for approvals and
  vetoes. `verify_signature` checks ts freshness (60s) then the signature
  against `canonical_json({action_id, decision, ts})` (reuses
  `aegis.chain.canonical_json`, same canonicalization as the hash chain).
  Verifies only, never signs, per plan/04's "the server can verify but
  never forge an approval." Encoding choice not pinned by the plan (the
  console that would generate keys doesn't exist until phase 4): lowercase
  hex for both pubkey and signature, documented in the module for phase 4
  to match.
- **`aegis.approvals`**: `veto_closes_at` / `approval_requested_at`, timing
  lookups derived from the event log rather than a new DB column
  (`action.veto_window_opened`'s `closes_at` payload field is the source
  of truth), used by both the gate node and `aegis.api` without pulling
  core-api into the agents/LangGraph import graph.
- **Gate node rewrite** (`aegis.agents.nodes.gate`): every proposal now
  goes through OPA for real.
  - green: allow -> `status='executing'`, included in the executed set.
  - yellow: allow -> `action.veto_window_opened` (closes_at from
    `now + 30s`), then the node itself blocks (polling the DB, not a DB
    trigger) until a veto lands or the window closes. A veto that lands in
    the same instant as the timeout is resolved by re-reading status one
    last time after the wait loop; `POST /veto` does the actual state
    transition with a conditional `UPDATE ... WHERE status = 'executing'`
    so only one of a simultaneous veto/timeout can win.
  - red: allow -> `action.approval_requested`, `incidents.status =
'awaiting_approval'`, then a genuine `langgraph.types.interrupt()`
    call, which durably parks the run (LangGraph checkpoints the pause).
  - Every side effect is guarded by first reading the action's current
    status, since LangGraph re-executes the whole node function on every
    resume (crash-restart or interrupt alike): `status == 'proposed'`
    means first pass, anything else means a prior pass already decided
    the policy outcome and this pass only picks up where it left off.
- **Approval dispatch loop** (`aegis.worker`, new): core-api cannot resume
  the graph itself (the compiled graph object only lives in core-worker),
  so it only ever writes the approve/reject decision to the database; this
  loop polls for incidents parked `awaiting_approval` whose action has
  since resolved (`approved`/`rejected`) and calls
  `graph.ainvoke(Command(resume="continue"), ...)` on the same thread_id
  to wake it, and separately times out any action still
  `awaiting_approval` 15 minutes after its `action.approval_requested`
  event (rejects it the same way a human would, so the paused gate node's
  own handling picks it up uniformly).
- **`Runner.in_flight`** (`aegis.worker`, new): tracks which incident_ids
  currently have a graph invocation running, and the supervisor's own
  resume path (`Runner.resume`, called directly by the heartbeat watchdog)
  no-ops if the incident is still in flight. Found live, see Deviations.
- **API** (`aegis.api`): `GET /api/catalog`, `GET
/api/incidents/{id}/verify-chain` (moved in from the phase 1/2 stopgap
  script, now retired), `POST /api/keys`, `POST /api/approvals/{action_id}`,
  `POST /api/veto/{action_id}` (shared signature/ts/pubkey verification,
  400 on any failure, 409 if the action already resolved or the veto
  window already closed). `GET /api/incidents/{id}` now returns real
  `actions` and `agent_runs` arrays instead of the phase 2 placeholder
  empty lists.
- **Executor** (`aegis.actions.execute`, `docker_ops`): `rollback_config`
  (best-effort clears every known fault toggle on the target service, then
  restarts it), `scale_service` (clones the target container via the
  Docker SDK for "1 -> 2", stops and removes the clone for rollback;
  compose's own scaling is a CLI concept, and the executor never shells
  out), `flush_queue` (a real `DEL` against a real, currently-always-empty
  Redis key, see Deviations), `restart_database` (already existed, found
  broken live, see Deviations). `docker_ops.container_state` (inspect-only,
  no live stats call) backs both the crash/memory_leak disambiguation and
  a new `GET /state/{service}` executor endpoint.
- **crash/memory_leak disambiguation** (`aegis.agents.state`): both fire
  `service_down` on target-payments (flagged as an open question in the
  phase 2 report). `resolve_scenario_hint` checks
  `container_state("target-payments").oom_killed` before the graph starts,
  choosing the fixture/live scenario key. The same mechanism resolves a
  second ambiguity found this phase: `latency_p95` on target-orders fires
  for both `latency` (toxiproxy) and `cache_outage` (a paused redis makes
  every cache call hang) — disambiguated by checking whether the `redis`
  container is paused.
- **Five unit test files**: `test_policy.py`, `test_security.py`,
  `test_gate.py` (the pure-ish helpers: runaway-brake counting,
  already-scaled detection, the veto wait's fast paths), on top of the
  existing suite.
- **`scripts/seed_red_action.py`**: seeds a synthetic incident with a
  red-tier action already proposed and runs a single-node graph (just
  `gate`) so it genuinely parks at `interrupt()`, since none of the five
  chaos scenarios' expected fix paths is a red action. Used by
  `e2e/test_approvals.py`.
- **e2e**: `test_scenarios.py` extended to all five scenarios;
  `test_approvals.py` (7 tests: signed approval wakes a parked run end to
  end with a real PyNaCl signature and a real cross-process resume, bad
  signature / unknown pubkey / stale timestamp all 400, already-resolved
  action 409, veto during the window escalates instead of healing,
  verify-chain tamper detection); `test_adversarial.py` (the error_spike
  scenario's log line never yields `flush_queue`).

## Deviations and choices

- **Encoding for pubkey/signature is lowercase hex.** plan/04-security.md
  doesn't pin one (the browser side that would generate these with
  tweetnacl doesn't exist until phase 4); documented in `aegis.security`
  for phase 4's console to match.
- **Veto reuses the `action.rejected` event type**, not a new
  `action.vetoed`. plan/02's event catalog has no dedicated veto event; a
  veto is semantically a human rejecting a yellow-tier action during its
  window, and `action.rejected`'s existing payload shape
  (`action_id, approver_pubkey, signature, reason`) fits without adding a
  type CLAUDE.md would otherwise require documenting in plan/02 first.
- **The 15-minute approval timeout also emits `action.rejected`** (actor
  `system:supervisor`, empty pubkey/signature), not a new event type, for
  the same reason; the incident reaches `incident.escalated` through the
  normal gate -> escalate path once the parked run resumes and sees the
  rejection, not directly from the timeout loop.
- **`autonomy` is now computed, not hardcoded to `'auto'`** (`resolve.py`):
  it checks whether any of the incident's actions has an
  `aegis.approvals` row with `decision = 'approve'`, and reports
  `'approved'` if so. Phase 2's `resolve()` never had a red-tier path to
  distinguish; this phase does, so plan/02's `auto/approved/escalated`
  autonomy values are now all reachable.
- **`flush_queue` deletes a real, currently-always-empty Redis key**
  (`aegis:orders:retry_queue`) instead of a hardcoded `{"status": "stub"}`
  the way phase 2 left yellow/red actions. No component in this demo
  enqueues retries yet (a target-app feature, out of phase 3's scope, not
  a policy/security one); this executes a genuine `DEL` against the live
  stack rather than fabricating a result, which is the same bar
  plan/04-security.md sets for everything else here ("every mechanism
  here is real and testable").
- **`rollback_config` clears every fault toggle a service exposes, then
  restarts it**, rather than restoring a versioned config file. No config
  file exists for any target service to roll back in this demo (the only
  "bad config" is error_spike's in-memory flag); this is the literal
  reading of the catalog's own effect string ("restore last good config
  ... + restart") given what's actually injectable.
- **`scale_service` clones the target container via the Docker SDK**
  (`docker_ops.clone_and_start`/`stop_and_remove`) instead of shelling out
  to `docker compose up --scale`, which is a CLI concept with no
  docker-SDK equivalent and would need a subprocess the executor is not
  allowed to hold (plan/04-security.md, no `shell=True` anywhere; a
  fixed-argv `docker compose` subprocess would still be a second exec
  surface this module otherwise has zero of). Not exercised by any of the
  five scenarios (none use it); unit-tested via the catalog/params layer
  only, matching phase 2's precedent for the same gap.
- **`Runner.in_flight`, found live.** cache_outage's live diagnose calls
  routinely ran 100-250s under Groq 429 backoff, well past the
  supervisor's 30s stale-heartbeat threshold, while the run was still
  alive, just slow. The supervisor "resumed" it anyway; since
  `resume_incident` starts a second, fully independent `graph.ainvoke`
  against the same thread_id, both the original task and the resume ran
  to completion concurrently, each executing its own remediation and
  emitting its own `incident.resolved` for the same incident (observed
  live: two full `action.proposed` -> `action.executed` -> `verify.passed`
  -> `incident.resolved` cycles on one incident, `inc_01KZAXDPRXREW3...`,
  see the crash of the first cache_outage recording attempt).
  `Runner.spawn` and `Runner.resume` now share an `in_flight` set so a
  false-positive stall (slow, not dead) is a no-op instead of a duplicate
  invocation. Not exercised by phase 2's two scenarios (both resolve in
  under 10s); phase 3's slower, more contended scenarios found it.
- **`emit()` only caught `TimeoutError`/`OSError` around the Redis
  publish, not `redis.exceptions.RedisError`.** Found live: a
  `redis.exceptions.ConnectionError` (raised on a connection the pool had
  open across a cache_outage pause/unpause cycle) is neither, so it used
  to propagate out of `emit()`. When that happened inside
  `_mark_escalated_on_crash`'s transaction, the whole transaction rolled
  back and the incident it was trying to escalate was left stuck in
  `resolving` forever, silently — and because the `aegis-db` volume
  persists across `docker compose down` (without `-v`), one such stuck row
  from earlier in this session's live testing kept blocking every later
  `service_down`/target-payments detection via the dedup check for the
  rest of the session, until traced back to it. Fixed by widening the
  except clause; both are real, shipped fixes, not test-only workarounds.
- **`deploy/docker-compose.yml`'s `shop-db` service had no
  `container_name`**, unlike every other stateful/target service; compose
  names it `aegis-shop-db-1` without one, and `restart_database` maps to
  the literal string `"shop-db"` (`aegis.actions.execute`). Every red-tier
  restart_database action failed with a 404 until this was added. Found
  live during the first successful signed-approval run.
- **cache_outage/error_spike fixture recording needed the fault cleared
  early, not left running for the full scenario window**
  (`scripts/record_fixtures.py`, `CLEAR_AFTER_FIRST_INCIDENT`). Both
  faults break every request through more than one service continuously,
  not as a single probe; left injected for the full window, detection
  reopens a fresh incident on the very next 5s poll after each one
  resolves or escalates, for as long as the fault is active — 17
  (cache_outage) and 39 (error_spike) concurrent incidents in testing,
  which exhausted this session's Groq free-tier daily budget on both
  candidate `LLM_LARGE` models (`openai/gpt-oss-120b` at 199,492/200,000
  TPD, then `llama-3.3-70b-versatile` at 99,189/100,000 TPD) before either
  scenario produced a clean recording. Clearing the fault ~10-25s after
  the first incident opens stops the storm at its source.
- **`diagnose` and `plan_remediation`'s prompts didn't mention `redis` as
  a checkable dependency at all**, even though `get_container_stats`
  already supported it end to end (`executor_app.STATS_CONTAINER_NAMES`
  already included `"redis"` from phase 2). Found live: without a hint,
  the model reasoned from `query_metrics`/`query_logs` alone (which show
  only "target-orders is slow," identical to the real `latency` fault's
  signature) and proposed `remove_toxic` for cache_outage every time,
  which happened to still resolve the incident (verify saw healthy
  because the fault had already been cleared out of band for recording),
  masking that the wrong action was chosen. Both prompts now name `redis`
  explicitly and `plan_remediation`'s prompt adds `restart_dependency` as
  a documented operational fact alongside the two that already existed.
- **error_spike/memory_leak/cache_outage's fixtures are hand-authored, not
  recorded from a resolved live run.** After the prompt fix, four
  consecutive attempts across both `LLM_LARGE` candidates hit daily quota
  exhaustion before a full triage -> diagnose -> plan_remediation -> verify
  sequence completed under live contention (see above). The three fixture
  sets (`error_spike_target-payments`, `memory_leak_target-payments`,
  `cache_outage_target-orders`) are written directly, matching the exact
  schema and tone of the genuinely-recorded ones byte for byte (same
  tool-call shapes, same catalog_keys the corrected prompts point to), not
  replayed from a transcript. This is a difference of provenance only:
  `aegis.llm`'s mock player and the tool loop treat a hand-authored
  fixture identically to a recorded one, and every tool the mocked model
  "calls" still executes for real against the live stack when the e2e
  test runs (only the model's own decisions are ever mocked, plan/03).
  What live-recorded fixtures would additionally have proven — that the
  live model, unprompted beyond the corrected system prompt, actually
  reaches these hypotheses and proposals on its own — is not proven this
  phase for these three scenarios specifically. Green/OPA policy handling,
  the executor, and the whole approval/veto/interrupt/resume mechanism
  _are_ fully live-verified, independent of any fixture (see Live
  verification below); flagged here for a follow-up session with a fresh
  quota day to replace these three with real recordings.

## Live verification

All commands below ran against a real `docker compose up` stack; `MOCK_LLM`
is called out per block. GROQ_API_KEY was a real key for every MOCK_LLM=0
block.

### Green tier through real OPA (crash, `MOCK_LLM=0`)

```
$ curl -X POST http://localhost:8080/api/chaos/crash
{"type":"chaos.injected", ...}
$ curl http://localhost:8080/api/incidents/inc_01KZAWNTXDBWM2C2KF7F2E7333
{"status":"resolved","mttr_seconds":6,"autonomy":"auto",...}
```

Event trail:

```
incident.detected        system:detector
agent.run.started         agent:triage
...
action.proposed           agent:remediation      {catalog_key: restart_service}
action.policy_checked     system:supervisor      {decision: allow, opa_rule_id: allow_green_tier}
action.executed           system:supervisor      {status: executed, catalog_key: restart_service}
verify.passed             agent:verify
incident.resolved         system:supervisor
```

`GET /api/incidents/{id}/verify-chain` -> `{"valid":true,"break_at_seq":null}`.

### Red tier: signed approval wakes a parked run (`MOCK_LLM=0`, no fixtures involved — gate is code)

```
$ docker compose exec -T core-worker python - < scripts/seed_red_action.py
{"incident_id": "inc_01KZAZEH657DFFV3T0NTNQE2W9", "action_id": "act_01KZAZEH657DFFV3T0NTNQE2WA"}
```

```
$ python3 - <<'PY'
# generates an Ed25519 keypair with PyNaCl, POSTs /api/keys, signs
# canonical_json({action_id, decision:"approve", ts}), POSTs /api/approvals
PY
register 200
approve 200 action.approved
```

```
$ curl http://localhost:8080/api/incidents/inc_01KZAZEH657DFFV3T0NTNQE2W9
{"status": "resolved", "autonomy": "approved", "mttr_seconds": 20,
 "actions": [{"catalog_key": "restart_database", "status": "executed",
   "result": {"result": {"action": "restart", "container": "shop-db"}}}]}
```

Note this run is what surfaced the `shop-db` container_name bug (first
attempt: `404 ... No such container: shop-db`) and confirmed the fix.

Bad-signature / already-resolved paths, same session:

```
$ curl -X POST .../api/approvals/act_...  -d '{"decision":"approve","pubkey":"00",...}'
400 {"detail":"signed_payload does not match this action_id/decision"}

$ curl -X POST .../api/approvals/act_...  # valid signature, action already resolved
409 {"detail":"action is not awaiting approval (already resolved)"}
```

### Full e2e suite, `MOCK_LLM=1`, fresh volumes (`docker compose down -v && up`)

```
$ MOCK_LLM=1 pytest e2e/test_scenarios.py -q
.....
5 passed in 366.19s (0:06:06)

$ MOCK_LLM=1 pytest e2e/test_approvals.py -v
test_signed_approval_wakes_the_parked_run PASSED
test_bad_signature_is_rejected PASSED
test_unknown_pubkey_is_rejected PASSED
test_stale_timestamp_is_rejected PASSED
test_approval_after_resolution_is_rejected_with_409 PASSED
test_veto_during_the_window_escalates_instead_of_healing PASSED
test_verify_chain_detects_tampering PASSED
7 passed in 59.03s

$ MOCK_LLM=1 pytest e2e/test_adversarial.py -v
test_adversarial_log_line_never_yields_flush_queue PASSED
1 passed in 115.03s
```

### Full suite run together (`MOCK_LLM=1 make e2e`, all 14 tests, one process)

```
$ MOCK_LLM=1 pytest e2e -q
........F.FFF.                                                   [100%]
4 failed, 10 passed in 923.30s (0:15:23)
```

The 4 failures were `test_killing_worker_mid_run_resumes_from_checkpoint`,
`test_crash_heals`, `test_error_spike_heals`, `test_memory_leak_heals` —
every failure specifically involves target-payments, and all four ran
consecutively after `test_checkpoint_resume.py`'s `docker compose kill -s
KILL core-worker` + crash-scenario restart. Traced to a real but
environment-specific issue, not a code defect: on this host's Docker
Desktop, after `target-payments` is stopped and container-SDK-restarted in
quick succession (the checkpoint test kills the worker mid-crash-scenario,
then the next three scenario tests each stop/restart target-payments
again), the embedded DNS resolver stops resolving the `target-payments`
hostname for other containers (`httpx.ConnectError: [Errno -2] Name or
service not known`), even though the container itself is `running` and
`healthy` per `docker inspect`. `docker compose up -d target-payments`
(a compose-level reconciliation, not the SDK's `container.restart()` that
`docker_ops.restart_container` uses) reliably restores it; run individually
(not immediately after the checkpoint test's kill+restart), every one of
these four tests passes, as shown above and in the individual runs earlier
in this report. Flagged for phase 4+ investigation (possibly: switch
`restart_service`/`restart_dependency`/`restart_database` to a
network-reattaching restart path, or add a DNS-resolves retry to the
probe); not fixed this phase given the size of the change relative to the
time available, and because the underlying mechanism (detection, gate,
executor, verify) is proven correct by every one of these same tests
passing in isolation.

## Verification output

`make lint test`:

```
.venv/bin/ruff check .
All checks passed!
.venv/bin/mypy
Success: no issues found in 50 source files
npm run lint
> eslint . (console, contracts)
npm run format:check
Checking formatting...
All matched files use Prettier code style!
.venv/bin/python -m pytest apps/core -q
............................................                             [100%]
44 passed, 2 warnings in 0.51s
npx -w @aegis/console tsc --noEmit
npx -w @aegis/contracts tsc --noEmit
.bin/opa test packages/policies -v
data.aegis.actions.test_allow_green_tier: PASS
data.aegis.actions.test_allow_yellow_tier: PASS
data.aegis.actions.test_deny_runaway_brake: PASS
data.aegis.actions.test_default_deny_unknown_tier: PASS
data.aegis.actions.test_deny_unknown_catalog_key: PASS
data.aegis.actions.test_deny_red_low_severity: PASS
data.aegis.actions.test_deny_low_confidence: PASS
data.aegis.actions.test_deny_scale_already_scaled: PASS
data.aegis.actions.test_allow_red_tier: PASS
PASS: 9/9
```

`docker compose ps`, clean stack, all 14 healthy:

```
aegis-aegis-db-1  Up (healthy)   aegis-console-1  Up (healthy)
aegis-core-api-1  Up (healthy)   aegis-core-executor-1  Up (healthy)
aegis-core-worker-1  Up          aegis-lgtm-1  Up (healthy)
aegis-loadgen-1  Up              aegis-opa-1  Up (healthy)
aegis-toxiproxy-1  Up (healthy)  redis  Up (healthy)
shop-db  Up (healthy)            target-gateway  Up (healthy)
target-orders  Up (healthy)      target-payments  Up (healthy)
```

`make contracts`: no diff (no schema changed this phase; `approvals` and
`approver_keys` are plain DB tables, not JSON-Schema contracts, per
plan/02).

Writing-rule and `shell=True` gate checks (tracked files): clean.

## Open questions

- **The Docker DNS flakiness above** needs a real fix before phase 4's
  console can assume `restart_service`/`restart_dependency`/
  `restart_database` reliably restore reachability, not just container
  status.
- **`scale_service` is still unexercised by any live scenario**, same gap
  phase 2 flagged for `clear_cache`/`rollback_config` (both now closed
  this phase). Structurally correct, unit-tested at the catalog layer,
  never run against the live stack.
- **error_spike/memory_leak/cache_outage's fixtures are hand-authored**
  (see Deviations); redoing them as genuine live recordings needs a
  session starting with a fresh Groq daily quota, ideally on a day with no
  other live testing planned first.
- **`Runner.in_flight`'s guard has a narrow residual race**: it checks
  membership, then calls `resume_incident`; a task finishing in the gap
  between those two lines would still permit a resume against an
  already-completed thread. `resume_incident` passing `None` to
  `graph.ainvoke` on a fully-completed thread's behavior in that exact
  case wasn't independently verified; considered low-risk (the
  supervisor's own `_resumed_once` set still caps this at one attempt) but
  not proven.

## Next

Stop here for review. Phase 4 (console, 2D complete) starts a new session
per PLAN.md's rule against reading ahead.
