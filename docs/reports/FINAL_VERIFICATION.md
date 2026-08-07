# Final verification

The runtime half of plan/07-review-and-launch.md, "Final full verification".
Static review passed separately; everything below needed a live Docker stack
or a real browser. Run on 2026-08-07 against `f35c5cf` and later, macOS
(darwin 25.3.0, arm64), Docker 28.4.0, Python 3.12.3, Chromium 1234 driven by
Playwright 1.62.1.

Every command output in this file is pasted from the run, not retyped.

Contents:

- [0. Post-review fixes](#0-post-review-fixes)
- [1. Stranger test](#1-stranger-test)
- [2. Fixture e2e from the clean clone](#2-fixture-e2e-from-the-clean-clone)
- [3. Live e2e](#3-live-e2e)
- [4. Red tier park, worker restart, resume](#4-red-tier-park-worker-restart-resume)
- [5. UI walkthrough](#5-ui-walkthrough)
- [6. Evidence pack](#6-evidence-pack)
- [Verdict](#verdict)

## 0. Post-review fixes

Two edits were already in the working tree when this run started, committed
as `d618bfe docs: post-review fixes from final verification`:

- `apps/target/payments/main.py`: one banned word in a comment ("leverage")
  replaced with "reach".
- `plan/02-contracts.md`: dropped the `verify.started` row from the event
  catalog. Checked before committing that nothing emits or consumes it:

```
$ grep -rn "verify.started\|verify_started\|VERIFY_STARTED" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.json" --include="*.md" . | grep -v node_modules
(no output)
```

## 1. Stranger test

Clean `git clone` into a scratch directory outside the repo, then README.md
only, nothing else read or assumed.

```
$ git clone /Users/naresh/Documents/AEGIS AEGIS
$ cd AEGIS && git log --oneline -1
d618bfe docs: post-review fixes from final verification
```

### Stack bring-up

The README's three quickstart commands, timed end to end:

```
### t0 = 2026-08-07T02:21:08Z
cp .env.example .env  0.00s user 0.00s system 66% cpu 0.006 total
### make up started 2026-08-07T02:21:08Z
[ -f .env ] || cp .env.example .env
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements-dev.txt -q
added 569 packages, and audited 572 packages in 6s
./packages/contracts/scripts/gen_python.sh
wrote apps/core/aegis/contracts/generated
npm run gen -w @aegis/contracts
wrote .../packages/contracts/generated/ts/index.ts
docker compose -f deploy/docker-compose.yml up -d --build
[...]
 Container aegis-core-worker-1  Started
 Container aegis-loadgen-1  Started
make up  10.64s user 7.54s system 40% cpu 44.390 total
### make up exit=0 2026-08-07T02:21:53Z
```

**44.4s** from `make up` to every container healthy, on a warm Docker build
cache (every layer logged `CACHED`; this machine had built the images
before). The README claims "typically inside 2 minutes on a warm build
cache", which holds. A genuinely cold image build was not measured here and
the README does not claim a number for one.

All 14 containers came up healthy:

```
$ docker ps --format '{{.Names}}\t{{.Status}}'
aegis-core-worker-1	Up 1 second
aegis-loadgen-1	Up 1 second
aegis-console-1	Up 7 seconds (healthy)
target-gateway	Up 7 seconds (healthy)
aegis-core-api-1	Up 14 seconds (healthy)
aegis-core-executor-1	Up 14 seconds (healthy)
target-orders	Up 14 seconds (healthy)
shop-db	Up 20 seconds (healthy)
aegis-aegis-db-1	Up 20 seconds (healthy)
redis	Up 20 seconds (healthy)
target-payments	Up 20 seconds (healthy)
aegis-lgtm-1	Up 20 seconds (healthy)
aegis-toxiproxy-1	Up 20 seconds (healthy)
aegis-opa-1	Up 20 seconds (healthy)
```

### Inject to heal, timed

Playwright drove a real Chromium at 1600x1000 doing exactly what the README
says: open localhost:3000, go to chaos, inject latency, watch the console.

```
t+0.8s  console loaded
t+0.9s  live data connected (metrics strip)
t+3.5s  chaos screen
t+5.1s  inject latency clicked
t+57.5s  incident detected (card appeared)
incident_id=inc_01KZD0GS7AGVX3NXY3VSA40GYW
t+58.3s  incident resolved (card reads resolved)
card=latency_p95 on target-orders |  | resolved | sev2 | 1s | auto |  | target-orders
DONE
```

Stage breakdown from the click: **52.4s to detection**, **0.8s from
detection to resolved**, **53.2s inject to heal**. The 52s is detection
latency, not agent latency: the rules engine waits on a PromQL `rate()[1m]`
window before the incident exists at all. Once open, the whole fixture-mode
loop (triage, diagnose, plan, propose, policy, execute, verify) took 1.1s of
wall clock, so `mttr_seconds` reads 1.

The heal was real, not a status flip. Full event log for that incident:

```
$ curl -s .../api/incidents/inc_01KZD0GS7AGVX3NXY3VSA40GYW/events
2026-08-07T02:23:31.052Z  system:detector            incident.detected
2026-08-07T02:23:31.784Z  agent:triage               agent.run.started
2026-08-07T02:23:31.795Z  agent:triage               agent.step
2026-08-07T02:23:31.800Z  agent:triage               agent.run.completed
2026-08-07T02:23:31.803Z  agent:triage               incident.classified
2026-08-07T02:23:31.807Z  agent:diagnose             agent.run.started
2026-08-07T02:23:31.811Z  agent:diagnose             agent.step
2026-08-07T02:23:31.814Z  agent:diagnose             agent.run.completed
2026-08-07T02:23:31.818Z  agent:plan_remediation     agent.run.started
2026-08-07T02:23:31.825Z  agent:plan_remediation     agent.step
2026-08-07T02:23:31.829Z  agent:plan_remediation     agent.run.completed
2026-08-07T02:23:31.837Z  agent:remediation          action.proposed
2026-08-07T02:23:31.902Z  system:supervisor          action.policy_checked
2026-08-07T02:23:32.061Z  system:supervisor          action.executed
2026-08-07T02:23:32.109Z  agent:verify               agent.run.started
2026-08-07T02:23:32.120Z  agent:verify               agent.step
2026-08-07T02:23:32.123Z  agent:verify               agent.run.completed
2026-08-07T02:23:32.160Z  agent:verify               verify.passed
2026-08-07T02:23:32.169Z  system:supervisor          incident.resolved
```

The executed action removed the injected toxic, and the chain verifies:

```
"catalog_key": "remove_toxic",
"params": {"toxic_name": "orders_shopdb_latency"},
"tier": "green",
"status": "executed",
"confidence": 0.800000011920929,
"policy_result": {"allow": true, "reason": "green tier auto-executes once no deny rule matches", "rule_id": "allow_green_tier"},
"result": {"result": {"toxic": "orders_shopdb_latency", "removed": true}, "status": "executed", "duration_ms": 106}

$ curl -s .../api/incidents/inc_01KZD0GS7AGVX3NXY3VSA40GYW/verify-chain
{"valid":true,"break_at_seq":null}
```

Recording: [docs/media/stranger-test.gif](../media/stranger-test.gif), the
whole 62s run from cold browser to resolved card.

### Defect 1 (low): README named a button that does not exist

The README said click **inject: latency**. The chaos screen actually shows
one card per scenario titled `latency`, each with an **inject fault**
button. Nothing is blocked by this (the card is right there, labelled
`latency`), but the README should name what is on screen. Fixed in
`docs: match README quickstart wording to the chaos screen`, which also
records the ~50s detection wait so a first-time reader does not think the
demo has hung.

## 2. Fixture e2e from the clean clone

`MOCK_LLM=1 make e2e`, run inside the same scratch clone, against the stack
that clone had just built.

### Defect 2 (medium): a clean clone could not run `make e2e` at all

First attempt, before any fix:

```
$ MOCK_LLM=1 make e2e
.venv/bin/python -m pytest e2e -q

==================================== ERRORS ====================================
____________________ ERROR collecting e2e/test_approvals.py ____________________
e2e/test_approvals.py:29: in <module>
    import nacl.signing
E   ModuleNotFoundError: No module named 'nacl'
__________________ ERROR collecting e2e/test_evidence_pack.py __________________
e2e/test_evidence_pack.py:20: in <module>
    from aegis.chain import next_hash
E   ModuleNotFoundError: No module named 'aegis'
=========================== short test summary info ============================
ERROR e2e/test_approvals.py
ERROR e2e/test_evidence_pack.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.10s
make: *** [e2e] Error 2
```

`make venv` installs `requirements-dev.txt` and stops there. The e2e suite
also needs the `aegis` package itself (`test_evidence_pack.py` recomputes
the chain with `aegis.chain.next_hash`) and PyNaCl (`test_approvals.py`
signs with it), both of which come from `apps/core`. Nobody noticed because
this repo's own `.venv` had been given `pip install -e apps/core` by hand
months of commits ago, and `.github/workflows/ci.yml` carried its own
`.venv/bin/pip install -e apps/core` line, so CI was green on a path a
clean clone never takes. Exactly the class of gap the stranger test exists
to catch.

Fixed in `f35c5cf fix(build): install apps/core into the venv so a clean
clone can run make e2e`: `make venv` now installs `-e apps/core` too, and
CI's private step was removed so CI exercises the same provisioning a clean
clone gets.

Verified from a second, untouched clone of the fixed tree:

```
$ git clone /Users/naresh/Documents/AEGIS AEGIS2 && cd AEGIS2 && git log --oneline -1
f35c5cf fix(build): install apps/core into the venv so a clean clone can run make e2e
$ cp .env.example .env && make venv
[...]
.venv/bin/pip install -e apps/core -q
make venv  8.80s user 2.27s system 66% cpu 16.587 total
### venv exit=0
$ .venv/bin/python -c "import nacl, aegis, pypdf; print('imports ok:', aegis.__file__)"
imports ok: .../AEGIS2/apps/core/aegis/__init__.py
```

### The suite

```
### fixture e2e start 2026-08-07T02:26:37Z
.venv/bin/python -m pytest e2e -q
...............                                                          [100%]
15 passed in 602.84s (0:10:02)
MOCK_LLM=1 make e2e  2.71s user 1.50s system 0% cpu 10:04.72 total
### exit=0
```

All 15 pass: 5 scenarios, 7 approval and chain-tamper cases, 1 adversarial
prompt-injection case, 1 checkpoint resume, 1 evidence pack.

### Defect 3 (medium, not fixed): collateral gateway incidents re-open every 5s

Noticed while watching the suite, not caused by it. `target-gateway`
proxies to `target-payments`, so breaking payments also breaks the gateway,
and a second incident opens on the gateway. That much is known and
documented (docs/reports/PHASE_2_REPORT.md). What is new here is what
happens next: those gateway incidents escalate almost immediately, and
`aegis.detection.loop._incident_open` only dedupes against
`status NOT IN ('resolved', 'escalated')`. An escalated incident stops
suppressing anything, so the next 5s poll opens another one, which
escalates, and so on for as long as the fault is injected.

Over the 10-minute fixture suite that produced 47 of them:

```
$ curl -s .../api/incidents?limit=200 | (tally by rule, service, status)
total incidents since make up: 80
  47  ('error_rate', ('target-gateway',), 'escalated')
  15  ('latency_p95', ('target-orders',), 'resolved')
   6  ('synthetic', (), 'resolved')
   4  ('latency_p95', ('target-gateway',), 'resolved')
   3  ('error_rate', ('target-payments',), 'resolved')
   2  ('service_down', ('target-payments',), 'resolved')
   1  ('service_down', ('target-payments',), 'open')
   1  ('latency_p95', ('target-gateway',), 'escalated')
   1  ('error_rate', ('target-payments',), 'escalated')

error_rate/target-gateway: 47 incidents, 02:27:17.821Z .. 02:33:34.021Z
```

A representative one, escalating 0.7s after detection with no action ever
proposed:

```
2026-08-07T02:31:58.188Z  system:detector        incident.detected
2026-08-07T02:31:58.910Z  agent:triage           agent.run.started
2026-08-07T02:31:58.915Z  agent:triage           incident.classified
2026-08-07T02:31:58.917Z  agent:diagnose         agent.run.started
2026-08-07T02:31:58.920Z  agent:diagnose         agent.run.completed
2026-08-07T02:31:58.923Z  agent:plan_remediation agent.run.started
2026-08-07T02:31:58.927Z  agent:plan_remediation agent.run.completed
2026-08-07T02:31:58.929Z  system:supervisor      incident.escalated
```

The proximate cause of the escalation, from the worker log, is fixture
exhaustion on the collateral incident's own replay sequence:

```
FileNotFoundError: no fixture at /app/fixtures/latency_target-gateway/diagnose_11.json;
  record with `make record-fixtures SCENARIO=latency_target-gateway`
During task with name 'diagnose' and id '1242a8da-c8e5-5e74-4e99-f184ab97cf3f'
```

Left unfixed on purpose. plan/03-agents-and-policy.md says only "dedupe
while an incident is open", so re-opening after an escalation is what the
spec asks for; adding an escalation cooldown, or scoping the gateway rules
so a downstream failure does not fire them, is a design decision for the
spec, not something to slip into a verification pass. Nothing is lost or
corrupted and no test fails. The cost is a demo-visible one: during a live
error_spike the incident feed fills with escalated gateway rows, one every
five seconds, next to the real incident.

## 3. Live e2e

Not verifiable on 2026-08-07. Both the committed `LLM_LARGE` and the one
substitute this pass was authorised to use had spent their Groq free-tier
daily token budget before the suite could finish. Recorded here in full
rather than smoothed over.

### Attempt 1, `llama-3.3-70b-versatile` (the `.env.example` default)

`MOCK_LLM=0` in `.env`, stack recreated so the containers picked it up
(`docker exec aegis-core-worker-1 printenv MOCK_LLM` returned `0`).

```
### live e2e retry 2026-08-07T02:39:04Z LLM_LARGE=llama-3.3-70b-versatile
MOCK_LLM=0 .venv/bin/python -m pytest e2e -q
[...]
FAILED e2e/test_approvals.py::test_veto_during_the_window_escalates_instead_of_healing
FAILED e2e/test_checkpoint_resume.py::test_killing_worker_mid_run_resumes_from_checkpoint
FAILED e2e/test_scenarios.py::test_latency_heals - AssertionError: {'id': 'in...
FAILED e2e/test_scenarios.py::test_crash_heals - AssertionError: {'id': 'inc_...
FAILED e2e/test_scenarios.py::test_error_spike_heals - TimeoutError: no incid...
FAILED e2e/test_scenarios.py::test_memory_leak_heals - AssertionError: {'id':...
FAILED e2e/test_scenarios.py::test_cache_outage_heals - AssertionError: {'id'...
7 failed, 8 passed in 494.16s (0:08:14)
```

Every failure is the same escalation, and the escalation reason names the
cause exactly:

```
2026-08-07T02:47:04.983Z  agent:diagnose  agent.run.started   {"model": "llama-3.3-70b-versatile", ...}
2026-08-07T02:47:14.222Z  agent:diagnose  agent.run.failed    {"reason": "Error code: 429 - {'error': {'message':
  'Rate limit reached for model `llama-3.3-70b-versatile` ... on tokens per day (TPD): Limit 100000, Used 99958 ...
2026-08-07T02:47:16.232Z  system:supervisor  incident.escalated {"reason": "agent run crashed: Error code: 429 ...
```

The 8 that passed are the ones that never call the large model: the
approval, signature-rejection, chain-tamper and adversarial cases.

### Attempt 2, `openai/gpt-oss-120b` (the authorised substitute)

Switched `LLM_LARGE`, recreated the stack, re-ran. Same wall, different
model:

```
Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01jvf...`
service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198702
```

### Attempt 3, one scenario on `openai/gpt-oss-20b`

A single test rather than the suite, to see whether any live path could be
demonstrated at all. It got further, three real diagnose tool calls against
live telemetry, before the per-minute budget ran out:

```
2026-08-07T03:01:00.979Z  agent:diagnose  agent.run.started  {"model": "openai/gpt-oss-20b", ...}
2026-08-07T03:01:01.583Z  agent:diagnose  agent.step  {"tool": "query_metrics", "service": "target-orders"}
2026-08-07T03:01:14.349Z  agent:diagnose  agent.step  {"tool": "query_logs", "service": "target-orders"}
2026-08-07T03:01:27.338Z  agent:diagnose  agent.step  {"tool": "get_container_stats", "service": "redis"}
2026-08-07T03:02:31.726Z  agent:diagnose  agent.run.failed  {"reason": "... on tokens per minute (TPM):
  Limit 8000, Used 6818, Requested 1692. Please try again in 3.825s ..."}
```

`aegis.llm` does retry 429s (`MAX_RATE_LIMIT_RETRIES = 3`, backoff 1s, 2s,
4s), which covers a 3.8s hint on its own. It did not help here because the
sibling incidents described in defect 3 were spending the same 8000 TPM
budget in parallel, so every retry met a fresh 429. That is the same
rate-limit contention PHASE_2_REPORT.md described, amplified by the number
of concurrent incidents.

Stopped there rather than working through a chain of further substitute
models. `.env` was restored to its committed defaults immediately after
(`MOCK_LLM=1`, `LLM_LARGE=llama-3.3-70b-versatile`), confirmed by diffing
it against `.env.example`:

```
$ diff <(redact .env) <(redact .env.example)
identical apart from redacted secrets
```

`.env` is gitignored (`.gitignore:1`) and was never staged.

**What this means for the release.** plan/07 asks for live MTTR within 20%
of the README's claims. That comparison could not be made today. The
README's live numbers come from PHASE_6_REPORT.md, which documents the same
quota wall being hit four times during collection, so this is a known and
already-disclosed constraint of a free-tier key, not a new finding. It does
mean the live path is unverified by this pass and someone should re-run
`make e2e-live` on a fresh daily budget before the tag moves.

## 4. Red tier park, worker restart, resume

Same mechanism as `e2e/test_approvals.py`: `scripts/seed_red_action.py`
runs a one-node graph inside core-worker so it parks at a real LangGraph
`interrupt()`, then the HTTP API drives the rest. The restart is verified
by container pid and `StartedAt`, and the new process must reach a live
detection poll before the approval is submitted, so "it resumed" cannot be
the old process finishing work it already had in flight.

```
[03:04:38.229Z] seeding a red-tier action and parking it at interrupt()
[03:04:39.406Z] parked incident=inc_01KZD2W3J0K7W03Q3G16VY11G5 action=act_01KZD2W3J0K7W03Q3G16VY11G6
[03:04:39.415Z] incident status=awaiting_approval action status=awaiting_approval
[03:04:39.416Z] events before restart: ['action.policy_checked', 'action.approval_requested']
[03:04:39.446Z] before restart: pid=38024 startedAt=2026-08-07T03:04:05.534511922Z
[03:04:39.446Z] restarting core-worker WHILE PARKED
[03:04:39.827Z] docker restart -> aegis-core-worker-1
[03:04:39.884Z] after restart:  pid=39795 startedAt=2026-08-07T03:04:39.756813174Z
[03:04:39.885Z] waiting for the new worker process to reach a live detection poll
[03:04:41.961Z] worker fully back up, 2.5s after restart began
[03:04:41.987Z] core-worker status: Up 2 seconds
[03:04:41.994Z] after restart, incident status=awaiting_approval (still parked, nothing lost)
[03:04:41.994Z] registering an approver key and submitting a signed approval
[03:04:42.002Z] key registered, fingerprint 032c887e
[03:04:42.009Z] POST /api/approvals -> 200 action.approved
[03:04:42.009Z] polling for resume
[03:04:46.041Z] resumed and finished: status=resolved autonomy=approved
[03:04:46.041Z] action status=executed result={"result": {"action": "restart", "container": "shop-db"}, "status": "executed", "duration_ms": 257}
```

The event log, with the restart window and the approval time alongside it:

```
ts                         actor                  type
2026-08-07T03:04:39.299Z   system:supervisor      action.policy_checked
2026-08-07T03:04:39.301Z   system:supervisor      action.approval_requested
2026-08-07T03:04:42.004Z   human:032c887e         action.approved
2026-08-07T03:04:45.754Z   system:supervisor      action.executed
2026-08-07T03:04:45.791Z   agent:verify           agent.run.started
2026-08-07T03:04:45.814Z   agent:verify           agent.step
2026-08-07T03:04:45.820Z   agent:verify           agent.run.completed
2026-08-07T03:04:45.846Z   agent:verify           verify.passed
2026-08-07T03:04:45.850Z   system:supervisor      incident.resolved

core-worker restart window: 2026-08-07T03:04:39.446520+00:00 .. 2026-08-07T03:04:41.961758+00:00
approval submitted at:      2026-08-07T03:04:42.002533+00:00
verify-chain: {"valid": true, "break_at_seq": null}

action.approved present: True
action.executed present: True
approved before executed: True
```

The order is the thing to read: the run parked, the process holding it died
and came back as a different pid, and the action only executed after a
signature arrived. Chain valid across the restart.

## 5. UI walkthrough

Playwright, headless Chromium at 1600x1000, against the running stack.
Screenshots in
[final-verification-screenshots/](final-verification-screenshots/).

### 3D renderer, inject to heal

```
== 3d: inject to heal ==
  topology-3d mounted (default renderer)
  screenshot 01-3d-healthy.png
  50 incident cards on screen before injecting
  screenshot 02-chaos-panel.png
  new incident inc_01KZD3B3E2G6BFGQW94HZ27K46 detected after 51.9s
  screenshot 03-3d-incident-active.png
  resolved after 53.5s
  card="latency_p95 on target-orders |  | resolved | sev2 | 1s | auto |  | target-orders"
  screenshot 04-3d-resolved.png
```

`04-3d-resolved.png` shows the detail panel with the executed
`remove_toxic`, `confidence 80%`, `opa: allow_green_tier`, and the four
agent-stream cards. It also shows the cost of defect 3 plainly: nine of the
twelve visible feed rows are escalated `error_rate on target-gateway`, and
the metrics strip reads `autonomy (auto) 22%` because of them.

### Forced 2D renderer

```
== 2d: ?view=2d ==
  topology-2d mounted, topology-3d count=0
  2d topology nodes rendered=5
  screenshot 05-2d-view.png
  2d: new incident inc_01KZD3BDAWTZ6KB52WAW5Z80HM detected after 4.1s
  still on the 2d renderer: topology-2d=1 topology-3d=0
  screenshot 06-2d-incident-active.png
  2d: resolved after 5.3s
  card="latency_p95 on target-orders |  | resolved | sev2 | 1s | auto |  | target-orders"
  screenshot 07-2d-resolved.png
```

### Defect 4 (medium): `?view=2d` did not survive an in-app navigation

The first run of this step reported `topology-2d=0 topology-3d=1` at the
line above. `?view=2d` is the escape hatch for a machine whose WebGL is
broken, and the chaos panel's own `router.push("/")` after injecting
dropped it, so pressing inject threw exactly that user onto the 3D canvas.
The nav links had the same hole.

Fixed in `18677df fix(console): carry an explicit ?view= override across
in-app navigation`: a `withViewParam` helper in `app/lib/viewParam.ts`,
applied in the chaos panel's push and the NavBar links, with three cases
added to `viewParam.test.ts`. The output above is the re-run after the fix.

### prefers-reduced-motion

Two checks, because reduced motion has two paths: the renderer it picks on
its own, and the 3D scene a user can still force with `?view=3d`.

```
== reduced motion, default renderer ==
  falls back to 2d: topology-2d=1 topology-3d=0
  topology elements sampled: 80, changed over 5s: 0
  running web animations while idle: []
== reduced motion, 3d scene forced with ?view=3d ==
  topology-3d mounted despite reduced motion (?view=3d wins, as designed)
  canvas pixels identical across a 4s idle gap: false
  (50463 vs 50446 bytes)
  running web animations while idle: []
== control: same 3d scene WITHOUT reduced motion ==
  canvas pixels identical across a 4s idle gap: false (expected false, it breathes)
```

The path a reduced-motion user actually gets is clean: the 2D renderer,
80 topology elements with zero geometry or opacity change across 5 idle
seconds, and zero running Web Animations.

### Defect 6 (low, not fixed): the forced 3D scene ignores reduced motion

`Topology3D` never calls `useReducedMotion`. Its `frameloop` is chosen from
incident activity alone, and `IdleTicker` keeps nudging the ambient traffic
pulse at 5fps, so with `?view=3d` set the scene animates identically
whether or not the user prefers reduced motion (the control run above
behaves the same). Reaching it takes an explicit opt-in to 3D, which is a
reasonable reading of "the user asked for this", so whether it should be
honoured anyway is a call for the spec rather than for a verification pass.
Left as found. Note that an earlier draft of this check also counted
`requestAnimationFrame` callbacks; that number measured the probe's own
loop, not the scene, and is not reported.

### Keyboard-only approval

No mouse, no programmatic focus, only `Tab` and `Enter`.

```
== keyboard-only approval overlay ==
  parked act_01KZD3PHWMRGGGBXGASZN1N7TJ with the console already open
  approval drawer present
  role=alertdialog aria-label="Red tier action awaiting approval"
  tab 1: {"tag":"A","text":"AEGIS","outline":"solid 2px rgb(34, 211, 238)"}
  tab 2: {"tag":"A","text":"console","outline":"solid 2px rgb(230, 237, 243)"}
  tab 3: {"tag":"A","text":"chaos","outline":"solid 2px rgb(139, 152, 165)"}
  tab 4: {"tag":"A","text":"metrics","outline":"solid 2px rgb(139, 152, 165)"}
  tab 5: {"tag":"BUTTON","text":"K","outline":"solid 2px rgb(139, 152, 165)"}
  tab 6: {"tag":"BUTTON","text":"synthetic red-tier test incident...","outline":"solid 2px rgb(230, 237, 243)"}
  tab 59: {"tag":"BUTTON","text":"approve","outline":"solid 2px rgb(5, 6, 7)"}
  reached the approve button with Tab alone: true (after 59 tabs)
  pressed Enter on the focused approve button
  incident inc_01KZD3PHWMRGGGBXGASZN1N7TH: status=resolved autonomy=approved
  action act_01KZD3PHWMRGGGBXGASZN1N7TJ: executed
    2026-08-07T03:19:05.967Z  system:supervisor  action.policy_checked
    2026-08-07T03:19:05.972Z  system:supervisor  action.approval_requested
    2026-08-07T03:19:06.502Z  human:462c5391  action.approved
    2026-08-07T03:19:10.380Z  system:supervisor  action.executed
    2026-08-07T03:19:10.425Z  agent:verify  agent.run.started
    2026-08-07T03:19:10.450Z  agent:verify  agent.step
    2026-08-07T03:19:10.456Z  agent:verify  agent.run.completed
    2026-08-07T03:19:10.511Z  agent:verify  verify.passed
    2026-08-07T03:19:10.521Z  system:supervisor  incident.resolved
  signed by a human actor: true
```

A keypress produced a real Ed25519 signature and a real container restart.
Every focusable element carries a visible focus outline; the approve
button's is the dark background token on the success fill, which measures
8.0:1, well over the 3:1 a focus indicator needs.

Two things the tab trace shows that are worth the reviewer's attention:

- The drawer is `role="alertdialog"` but sets no initial focus and traps
  none, so it sits at the end of the tab order behind the whole incident
  feed. 59 tabs is a function of defect 3 having filled that feed with 50
  escalated rows; on a clean feed it is 6. Correct-but-slow rather than
  broken, and the fix (autofocus plus a focus trap) is a design change.
- `11-approval-signed.png` catches the drawer already unmounting: the
  drawer's own "approved, signed <fingerprint>" confirmation is only on
  screen between the POST returning and the resolution event arriving,
  about a second in fixture mode.

### Defect 5 (high, not fixed): a parked approval is invisible after a page reload

Found while setting the keyboard pass up. `ApprovalOverlays` folds
`foldAllIncidents({}, events)` over live WebSocket events only, with no
seed, and `/ws/events` live-tails Redis from `$` with no backfill. So the
drawer only ever renders for a park that happens while the page is already
open.

Three cases, same stack, same browser:

```
== case A: parked before page load ==
  API says incident=awaiting_approval action=awaiting_approval
  approval-drawer on screen: false
  its incident card is in the feed: true
  card reads: "synthetic red-tier test incident |  | awaiting approval | sev1"
== case B: parked while the page is open ==
  approval-drawer appeared live: true
== case C: reload while still parked ==
  approval-drawer after reload: false
  API still says incident=awaiting_approval action=awaiting_approval
```

Nothing is lost: the run stays parked, the API still reports it, and the
incident feed still shows "awaiting approval" (the feed seeds from REST via
`useIncidentViews`, which the overlay does not). But the approve and reject
buttons live only in that drawer, `ActionCard` and `DetailPanel` have no
approval control, so after a refresh there is no way to approve a red-tier
action from the UI at all. The operator has to keep the tab that saw the
park, or fall back to `POST /api/approvals/{id}` by hand.

This is the human-oversight path the project leads with, so it is the most
serious thing this pass found. Left unfixed deliberately: the two candidate
fixes are a backfill handshake on `/ws/events` (server plus client) or a
REST read inside `ApprovalOverlays`, and the second contradicts CLAUDE.md's
"components select, never fetch live data ad hoc". Which one is right is a
design decision, and plan/07 says defects found here reopen phase 6.

### Flight recorder

```
== flight recorder ==
  chain badge: "chain verified"
  scrubber range: 0..18
  index 0: current="1/19 · incident.detected" action cards=0 (events section present=true)
  index 6: current="7/19 · agent.step" action cards=0 (events section present=true)
  index 12: current="13/19 · action.policy_checked" action cards=1 (events section present=true)
  index 18: current="19/19 · incident.resolved" action cards=1 (events section present=true)
  chain badge after scrubbing: "chain verified"
```

Scrubbing is a real as-of-t derivation, not a highlight: at index 0 there
are no action cards because no action had been proposed yet, and one
appears at index 12 where `action.policy_checked` lands. The chain badge
reads `chain verified` before and after scrubbing.

## 6. Evidence pack

Downloaded, extracted and read for one auto-resolved and one approved
incident. Chain re-verification recomputes `aegis.chain.next_hash` over the
downloaded `events.jsonl` rather than re-asking the API.

```
========================================================================
auto-resolved: inc_01KZD3B3E2G6BFGQW94HZ27K46
========================================================================
status=resolved autonomy=auto mttr=1s
GET evidence-pack -> 200 application/zip
content-disposition: attachment; filename="evidence-pack-inc_01KZD3B3E2G6BFGQW94HZ27K46.zip"
zip size: 9246 bytes
members: ['events.jsonl', 'report.pdf']

PDF: 3 pages, 7093 chars of extractable text
policy rule_id 'allow_green_tier' in PDF: True
signer fingerprints: none (no approval or veto on this incident)
Article 12 section in PDF: True
Article 14 section in PDF: True
Article 73 section in PDF: True

events.jsonl: 19 lines, chain recomputed with aegis.chain.next_hash
chain valid: True
same ids and order as the live event log: True
tamper check, recomputed hash differs after editing line 1: True

========================================================================
approved: inc_01KZD3PHWMRGGGBXGASZN1N7TH
========================================================================
status=resolved autonomy=approved mttr=4s
GET evidence-pack -> 200 application/zip
content-disposition: attachment; filename="evidence-pack-inc_01KZD3PHWMRGGGBXGASZN1N7TH.zip"
zip size: 6471 bytes
members: ['events.jsonl', 'report.pdf']

PDF: 2 pages, 4082 chars of extractable text
policy rule_id 'allow_red_tier' in PDF: True
signer fingerprint 462c53913a585a87... in PDF: True
Article 12 section in PDF: True
Article 14 section in PDF: True
Article 73 section in PDF: True

events.jsonl: 9 lines, chain recomputed with aegis.chain.next_hash
chain valid: True
same ids and order as the live event log: True
tamper check, recomputed hash differs after editing line 1: True
```

The automated report also listed `action.policy_checked` and
`action.approval_requested` as "missing from the PDF". That was an artifact
of matching substrings against `pypdf`-extracted text: ReportLab wraps long
values mid-token, so the timeline cell reads `action.policy_check` / `ed`
across two lines. Reading the extracted text by hand confirms both events
are present with full payloads. From the approved pack:

```
Full timeline
EU AI Act Article 12: record-keeping
3252  2026-08-07T03:19:05.967Z  action.policy_checked  system:supervisor
      {"action_id": "act_01KZD3PHWMRGGGBXGASZN1N7TJ", "decision": "allow", "opa_rule_id": "allow_red_tier"}
3253  2026-08-07T03:19:05.972Z  action.approval_requested  system:supervisor
      {"action_id": "...", "diff": {"catalog_key": "restart_database", "params": {}}, "reasoning": "synthetic e2e test action"}
3254  2026-08-07T03:19:06.502Z  action.approved  human:462c5391
      {"action_id": "...", "approver_pubkey": "462c53913a585a87e9a138d553c05a497f98d752cb10489a6118d14337be4eec",
       "signature": "1266ac5b1271822fcc09d5a31d5464fd664d3011ca7fa23ecf5cd3b94e833be926977a5ac7c46cce80d357836a109b84f259a355fb9e123b4fd2b2a3818eef04"}

Actions and policy decisions
act_01KZD3PHWMRGGGBXGASZN1N7TJ  restart_database  red  executed  0.95  allow (allow_red_tier)

Approvals and vetoes
EU AI Act Article 14: human oversight
act_01KZD3PHWMRGGGBXGASZN1N7TJ  approve  2c4ff8c66317323a  1266ac5b1271822fcc09d5a31d5464fd...  2026-08-07T03:19:06.501Z

Chain verification
Hash chain result: valid, no break detected.
```

The signer fingerprint column is `sha256(pubkey bytes)[:16]`, not a prefix
of the key, which is why an automated prefix search would miss it.
Reproduced independently:

```
$ python -c "import hashlib; print(hashlib.sha256(bytes.fromhex(PUBKEY)).hexdigest()[:16])"
2c4ff8c66317323a      <- matches the PDF
```

### Defect 7 (low): the PDF rendered an em dash

`apps/core/aegis/evidence_pack.py` built its subtitle with the HTML entity
`&mdash;`, which ReportLab renders as a real em dash into every generated
PDF. The repo-wide gate stayed green the whole time because the source only
ever contained the entity:

(written with the byte escape below rather than the character itself, so
this report does not trip the very gate it is describing; `scripts/gate.sh`
line 29 uses the same escape for the same reason)

```
$ grep -rn $'\xe2\x80\x94' . --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.next
plan/07-review-and-launch.md:13:5. Writing rules: zero em dashes repo-wide (...)
```

The single hit is plan/07 quoting the character in its own instruction, and
`gate.sh` excludes `plan/` anyway. CLAUDE.md says no em dashes anywhere, and
the PDF is shipped output. Fixed in `d993d1a fix(core): drop the em dash
entity from the evidence pack PDF subtitle`. Both packs regenerated
afterward and re-checked:

```
$ grep -c $'\xe2\x80\x94' packs2/*/report.txt
packs2/auto-resolved/report.txt:0
packs2/approved/report.txt:0
```

`grep -rn "&mdash;\|&ndash;\|&#8212;\|&#8211;"` over the repo returns
nothing else.

## Full lint and test after the fixes

```
### make lint test 2026-08-07T03:51:40Z
All checks passed!                       (ruff)
Success: no issues found in 51 source files   (mypy)
47 passed, 2 warnings in 1.15s           (pytest apps/core)
 Test Files  6 passed (6)
      Tests  36 passed (36)              (vitest, console)
PASS: 9/9                                (opa test)
### exit=0
```

`npm run lint`, `npm run format:check` and both `tsc --noEmit` passes are
clean; the fixture e2e run in section 2 was 15/15.

## Verdict

Not clean. Five of the six runtime checks pass; one could not be run, and
seven defects came out of the pass, of which four are fixed and three are
left for a decision that is not a verifier's to make.

plan/07 says "the release tag moves only when this list is clean", so no
tag was moved, nothing was pushed, and nothing was published. Defect 5 in
particular should be settled before launch: it breaks the human-oversight
story the README leads with.

### Check results

| Check                                                          | Result                                               |
| -------------------------------------------------------------- | ---------------------------------------------------- |
| 1. Stranger test (clean clone, README only)                    | pass, 44.4s to a healthy stack, 53.2s inject to heal |
| 2. Fixture e2e from the clean clone                            | pass, 15/15 in 10m02s, after fixing defect 2         |
| 3. Live e2e (`MOCK_LLM=0`)                                     | **not verifiable**, Groq daily quota exhausted       |
| 4. Red tier park, restart, resume                              | pass                                                 |
| 5. UI walkthrough (3D, 2D, reduced motion, keyboard, recorder) | pass, after fixing defect 4                          |
| 6. Evidence pack (auto and approved)                           | pass, after fixing defect 7                          |

### Defects found

| #   | Severity | What                                                                                                                                      | Status |
| --- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 5   | high     | A parked red-tier approval is invisible after a page reload; no approve control exists outside the live-only overlay                      | open   |
| 2   | medium   | A clean clone could not run `make e2e`; `make venv` never installed `apps/core`, and CI hid it with a private step                        | fixed  |
| 3   | medium   | Collateral gateway incidents re-open every 5s while a fault is active (47 in one 10-minute suite), flooding the feed and the token budget | open   |
| 4   | medium   | `?view=2d` was dropped by the chaos panel's push and by the nav links                                                                     | fixed  |
| 1   | low      | README named an **inject: latency** button that does not exist on the chaos screen                                                        | fixed  |
| 6   | low      | The 3D scene forced on with `?view=3d` ignores prefers-reduced-motion                                                                     | open   |
| 7   | low      | `&mdash;` in the evidence-pack source rendered a real em dash into every PDF, invisible to the repo-wide grep                             | fixed  |

### Fixes committed

All on `phase-6`, none pushed:

```
d618bfe docs: post-review fixes from final verification
f35c5cf fix(build): install apps/core into the venv so a clean clone can run make e2e
eeabcaa docs: match README quickstart wording to the chaos screen
18677df fix(console): carry an explicit ?view= override across in-app navigation
d993d1a fix(core): drop the em dash entity from the evidence pack PDF subtitle
```

`f35c5cf` also drops CI's own `pip install -e apps/core` so CI exercises
the same provisioning a clean clone gets. `18677df` adds three cases to
`apps/console/app/lib/viewParam.test.ts`.

### Left open, and why

- **Defect 5 (parked approval invisible after reload).** Both candidate
  fixes are design changes: a backfill handshake on `/ws/events`, or a REST
  read inside `ApprovalOverlays` that would contradict CLAUDE.md's single
  WebSocket store rule. Needs a decision, then an e2e test that reloads the
  page mid-park.
- **Defect 3 (incident re-open storm).** plan/03 specifies dedupe only
  "while an incident is open", so re-opening after an escalation is what
  the spec asks for. An escalation cooldown, or scoping the gateway rules
  so a downstream failure does not fire them, changes specified behaviour.
  Worth deciding before a demo: it is what put 50 escalated rows in the
  feed screenshot and dragged the metrics strip to `autonomy (auto) 22%`.
- **Defect 6 (3D scene under reduced motion).** Only reachable by
  explicitly asking for 3D, so honouring the preference anyway is a
  judgement call for the spec.

### Not verified

- **Live LLM behaviour of any kind.** `llama-3.3-70b-versatile` (TPD limit 100000) and `openai/gpt-oss-120b` (TPD limit 200000) were both spent
  before this pass ran; `openai/gpt-oss-20b` got three diagnose tool calls
  in before its per-minute budget went too. No live MTTR number was
  produced, so the README's measured table could not be checked against the
  20% band plan/07 asks for. Re-run `make e2e-live` on a fresh daily budget.
- **A cold Docker image build.** Every layer in the stranger test logged
  `CACHED`, because this machine had built the images before. The README
  only claims a warm-cache number, which held at 44.4s, but a first-ever
  clone on a clean machine remains unmeasured.
- **The `crash` scenario through the 2D UI specifically.** That step caught
  a concurrent `latency_p95` incident rather than the crash one and healed
  that instead. The 2D renderer assertion (it stays 2D, it shows the loop
  reaching resolved) holds either way, and `test_crash_heals` passes in the
  fixture suite.
