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
- [Phase 7 addendum](#phase-7-addendum)
- [Live verification](#live-verification)
- [Phase 9](#phase-9)

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
spec, not something to slip into a verification pass.

**Severity raised to high after section 3.** On fixtures this looks like
cosmetic noise, since nothing is lost, no test fails, and the only visible
cost is an incident feed full of escalated gateway rows. The live run
measured what it actually costs: 60 incidents opened in nine minutes, 49
of them escalating, and 79% of a 100,000-token daily budget spent on
incidents that were never going to heal. That is what stops
`make e2e-live` from finishing on a free-tier key. See section 3 for the
numbers.

## 3. Live e2e

Partially verified. On a fresh Groq key the live path demonstrably works,
10 of 15 tests pass, and five incidents healed end to end against real
model calls. The suite still does not finish, and this run finally shows
why with numbers: defect 3's re-open storm spends the entire free-tier
daily token budget in nine minutes.

Run three times in total. All three are recorded below, because the first
two are what made the third interpretable.

### Attempts 1 and 2, on the original key: no budget left to test with

`MOCK_LLM=0` in `.env`, stack recreated so containers picked it up
(`docker exec aegis-core-worker-1 printenv MOCK_LLM` returned `0`).

```
### live e2e 2026-08-07T02:39:04Z LLM_LARGE=llama-3.3-70b-versatile
MOCK_LLM=0 .venv/bin/python -m pytest e2e -q
[...]
7 failed, 8 passed in 494.16s (0:08:14)
```

Every failure was the same escalation, and the reason named the cause:

```
2026-08-07T02:47:04.983Z  agent:diagnose  agent.run.started   {"model": "llama-3.3-70b-versatile", ...}
2026-08-07T02:47:14.222Z  agent:diagnose  agent.run.failed    {"reason": "Error code: 429 - {'error': {'message':
  'Rate limit reached for model `llama-3.3-70b-versatile` ... on tokens per day (TPD): Limit 100000, Used 99958 ...
2026-08-07T02:47:16.232Z  system:supervisor  incident.escalated {"reason": "agent run crashed: Error code: 429 ...
```

Switching `LLM_LARGE` to the authorised substitute `openai/gpt-oss-120b`
hit the same wall on that model's own budget:

```
Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01jvf...`
service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198702
```

A single scenario on `openai/gpt-oss-20b` got three real diagnose tool
calls in before its per-minute budget went too. Nothing about the system
was tested by any of this: the day's budget had already been spent by
earlier phase-5 and phase-6 work.

### Attempt 3, fresh key, committed default model

A second Groq key was supplied with an untouched daily budget, confirmed
before spending anything on it:

```
$ curl -sD - .../chat/completions -d '{"model":"llama-3.3-70b-versatile",...}'
HTTP/2 200
x-ratelimit-limit-requests: 1000
x-ratelimit-remaining-requests: 999
x-ratelimit-limit-tokens: 12000
x-ratelimit-remaining-tokens: 11958
```

`LLM_LARGE` back to the committed `llama-3.3-70b-versatile`, all chaos
scenarios cleared first, stack recreated:

```
### live e2e, fresh key 2026-08-07T04:06:58Z LLM_LARGE=llama-3.3-70b-versatile
MOCK_LLM=0 .venv/bin/python -m pytest e2e -q
[...]
FAILED e2e/test_approvals.py::test_veto_during_the_window_escalates_instead_of_healing
FAILED e2e/test_scenarios.py::test_latency_heals - AssertionError: {'id': 'in...
FAILED e2e/test_scenarios.py::test_error_spike_heals - AssertionError: {'id':...
FAILED e2e/test_scenarios.py::test_memory_leak_heals - AssertionError: {'id':...
FAILED e2e/test_scenarios.py::test_cache_outage_heals - AssertionError: {'id'...
5 failed, 10 passed in 545.64s (0:09:05)
make: *** [e2e-live] Error 1
```

10 passed, up from 8. `test_crash_heals` and
`test_killing_worker_mid_run_resumes_from_checkpoint` both pass against
live model calls, so checkpoint resume is now verified live as well as on
fixtures.

### Live MTTR actually measured

Eleven incidents resolved during the run. The five real ones (the six
`synthetic` rows are the seeded red-tier approvals, not chaos scenarios):

| Rule                            | MTTR | Autonomy |
| ------------------------------- | ---- | -------- |
| latency_p95 on target-orders    | 93s  | auto     |
| latency_p95 on target-orders    | 35s  | auto     |
| latency_p95 on target-gateway   | 32s  | auto     |
| service_down on target-payments | 47s  | auto     |
| service_down on target-payments | 42s  | auto     |

Against the README's live table: latency is claimed at 92s and measured
93s here, inside 2%. The `service_down` rows measured 47s and 42s against
a claimed 61s for crash, faster than claimed and outside the 20% band on
the fast side; note `service_down` fires for both crash and memory_leak
(PHASE_2_REPORT.md, Open questions), so those two rows cannot be
attributed to one scenario with confidence. `error_spike` and
`cache_outage` produced no resolved sample, so their README numbers remain
unchecked by this pass.

### Why the suite still does not finish, measured

The failure is not the model and not the code. It is volume. Counting
every incident opened inside the 9m05s window:

```
incidents opened during the 9m05s live run: 60
   19  ('error_rate', ('target-gateway',), 'escalated')
   16  ('error_rate', ('target-payments',), 'escalated')
    6  ('synthetic', (), 'resolved')
    5  ('latency_p95', ('target-gateway',), 'escalated')
    5  ('latency_p95', ('target-orders',), 'escalated')
    2  ('error_rate', ('target-orders',), 'escalated')
    2  ('service_down', ('target-payments',), 'escalated')
    2  ('latency_p95', ('target-orders',), 'resolved')
    2  ('service_down', ('target-payments',), 'resolved')
    1  ('latency_p95', ('target-gateway',), 'resolved')

agent runs: 157, tokens_in 127325, tokens_out 7744, total 135069, cost $0.0555
```

Split by outcome:

```
escalated   49 incidents   106738 tokens  79%
resolved    11 incidents    28331 tokens  21%
total       60 incidents   135069 tokens
```

The suite needs five scenarios healed. It opened 60 incidents and spent
135,069 tokens against a 100,000 daily limit, and **79% of that went to 49
incidents that escalated**, nearly all of them defect 3's five-second
re-opens. The eleven incidents that actually resolved cost 28,331 tokens,
comfortably inside the free-tier day.

The exhaustion message, from the first incident to hit it:

```
Rate limit reached for model `llama-3.3-70b-versatile` in organization
`org_01kw5e8rn2ejd8b7mt7hfr6rs0` service tier `on_demand` on tokens per day (TPD):
Limit 100000, Used 98997, Requested 1386. Please try again in 5m30.912s.
```

So the honest reading is not "the free tier is too small for this demo".
It is that the storm multiplies the demo's real cost by roughly five, and
that is what puts it over the line. Fixing defect 3 is very likely enough
to make `make e2e-live` pass on a free-tier key; that is a prediction from
these numbers, not something this pass verified.

### What is still unverified

`error_spike` and `cache_outage` never produced a live resolution, so two
of the README's five measured rows are unchecked. A clean full-suite live
run needs either a paid tier or defect 3 fixed first. `.env` was restored
to `MOCK_LLM=1` with the committed default model immediately afterward,
verified by diffing against `.env.example`:

```
$ diff <(redact .env) <(redact .env.example)
identical apart from redacted secrets
```

`.env` is gitignored (`.gitignore:1`) and was never staged. The supplied
key is left in the local `.env` only, since the original key is spent; the
original file is backed up outside the repo.

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

Not clean. Five of the six runtime checks pass, one is partially verified,
and seven defects came out of the pass, of which four are fixed and three
are left for a decision that is not a verifier's to make.

plan/07 says "the release tag moves only when this list is clean", so no
tag was moved, nothing was pushed, and nothing was published.

Two things should be settled before launch. Defect 5 breaks the
human-oversight story the README leads with: refresh the page and a parked
red-tier approval becomes unapprovable from the UI. Defect 3 is what keeps
`make e2e-live` from finishing, and the live run put a number on it,
79% of a daily token budget spent on incidents that were never going to
heal.

### Check results

| Check                                                          | Result                                               |
| -------------------------------------------------------------- | ---------------------------------------------------- |
| 1. Stranger test (clean clone, README only)                    | pass, 44.4s to a healthy stack, 53.2s inject to heal |
| 2. Fixture e2e from the clean clone                            | pass, 15/15 in 10m02s, after fixing defect 2         |
| 3. Live e2e (`MOCK_LLM=0`)                                     | **partial**, 10/15 on a fresh key, 5 live heals      |
| 4. Red tier park, restart, resume                              | pass                                                 |
| 5. UI walkthrough (3D, 2D, reduced motion, keyboard, recorder) | pass, after fixing defect 4                          |
| 6. Evidence pack (auto and approved)                           | pass, after fixing defect 7                          |

### Defects found

Statuses updated by phase 7; see the [phase 7 addendum](#phase-7-addendum)
for the code and the pasted output behind each of the three that changed.

| #   | Severity | What                                                                                                                                                                               | Status          |
| --- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| 5   | high     | A parked red-tier approval is invisible after a page reload; no approve control exists outside the live-only overlay                                                               | fixed (phase 7) |
| 3   | high     | Incidents re-open every 5s while a fault is active (60 in one 9-minute live run); 79% of the daily token budget goes to escalating duplicates, which is what stops `make e2e-live` | fixed (phase 7) |
| 2   | medium   | A clean clone could not run `make e2e`; `make venv` never installed `apps/core`, and CI hid it with a private step                                                                 | fixed           |
| 4   | medium   | `?view=2d` was dropped by the chaos panel's push and by the nav links                                                                                                              | fixed           |
| 1   | low      | README named an **inject: latency** button that does not exist on the chaos screen                                                                                                 | fixed           |
| 6   | low      | The 3D scene forced on with `?view=3d` ignores prefers-reduced-motion                                                                                                              | fixed (phase 7) |
| 7   | low      | `&mdash;` in the evidence-pack source rendered a real em dash into every PDF, invisible to the repo-wide grep                                                                      | fixed           |

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

All three were closed by phase 7; this section is what that pass was
handed, kept as written. The decisions it asks for were made in the
amended plan/03 and plan/05, and the work is in the
[phase 7 addendum](#phase-7-addendum).

- **Defect 5 (parked approval invisible after reload).** Both candidate
  fixes are design changes: a backfill handshake on `/ws/events`, or a REST
  read inside `ApprovalOverlays` that would contradict CLAUDE.md's single
  WebSocket store rule. Needs a decision, then an e2e test that reloads the
  page mid-park.
- **Defect 3 (incident re-open storm).** plan/03 specifies dedupe only
  "while an incident is open", so re-opening after an escalation is what
  the spec asks for. An escalation cooldown, or scoping the gateway rules
  so a downstream failure does not fire them, changes specified behaviour.
  This is the one to fix first. It put 50 escalated rows in the feed
  screenshot, dragged the metrics strip to `autonomy (auto) 22%`, and
  spent 79% of a free-tier daily token budget in nine minutes. The eleven
  incidents that actually resolved in that run cost 28,331 tokens against
  a 100,000 limit, so fixing it is very likely enough to make
  `make e2e-live` pass on a free key. Worth an e2e test that counts
  incidents opened per injected fault.
- **Defect 6 (3D scene under reduced motion).** Only reachable by
  explicitly asking for 3D, so honouring the preference anyway is a
  judgement call for the spec.

### Not verified

- **A full clean `make e2e-live`.** The best run was 10/15 on a fresh key,
  with five real live heals. `error_spike` and `cache_outage` produced no
  resolved sample, so two of the README's five measured rows stay
  unchecked. `latency` measured 93s against a claimed 92s; the
  `service_down` rows measured 47s and 42s against a claimed 61s for
  crash, outside the 20% band on the fast side and not cleanly attributable
  because `service_down` covers both crash and memory_leak. Re-run after
  defect 3 is fixed, or on a paid tier.
- **A cold Docker image build.** Every layer in the stranger test logged
  `CACHED`, because this machine had built the images before. The README
  only claims a warm-cache number, which held at 44.4s, but a first-ever
  clone on a clean machine remains unmeasured.
- **The `crash` scenario through the 2D UI specifically.** That step caught
  a concurrent `latency_p95` incident rather than the crash one and healed
  that instead. The 2D renderer assertion (it stays 2D, it shows the loop
  reaching resolved) holds either way, and `test_crash_heals` passes in the
  fixture suite.

## Repo gate after every fix

`scripts/gate.sh 6` re-run on `2bbf64a`, with all four fixes and this report
in the tree. It re-runs the em dash and security greps, `make lint test`,
and the full fixture e2e:

```
### gate.sh 6 rerun 2026-08-07T03:47:13Z
gate: phase 6 clean
### exit=0

$ tail -3 /tmp/gate_e2e.log
.venv/bin/python -m pytest e2e -q
...............                                                          [100%]
15 passed in 602.34s (0:10:02)
```

The first run of the gate did fail, on `prettier --check` against this file
before it was formatted. Recorded because the rule is that pasted output is
the evidence: the failure was in the report's own markdown, not in the code.

## State this pass left behind

- Branch `phase-6`, four fix commits plus this report. Nothing pushed, no
  remote touched, no tag created or moved. `phase-6` still points where it
  did.
- `.env` restored to `MOCK_LLM=1` and the committed default model, and
  never staged. It holds the second Groq key, since the first is spent for
  the day; the original file is backed up outside the repo.
- The stack is up in fixture mode (`MOCK_LLM=1`). `make down` clears it,
  including the incident rows this pass generated.

## Phase 7 addendum

Run on 2026-08-07, branch `phase-7` off `phase-6`, same machine and stack
as the rest of this report. Phase 7 closes defects 3, 5 and 6 against the
amended specs in plan/03-agents-and-policy.md (Detection) and
plan/05-frontend.md (Fallback, Frontend data layer). Every command output
below is pasted from the run.

The e2e suite goes from 15 tests to 18: one per fixed defect.

### Defect 3, one incident per (rule, service) per firing episode

`aegis.detection.loop` no longer decides by SQL status. `DetectionState`
carries an `episode_open` set of (rule, service) pairs, an incident sets
the flag, and only a clean evaluation of that rule clears it, so an
incident that escalates a second after opening keeps suppressing its own
episode for as long as the metric stays over threshold.
`rebuild_episode_state()` reloads the flags from the incidents table
before the first poll, skipping resolved rows because a resolution already
implies verify probes came back clean:

```
$ docker logs aegis-core-worker-1 | grep episodes
2026-08-07 05:00:19,376 worker detection: 6 firing episodes rebuilt from the incidents table
```

Six unit cases drive the loop's own poll path with a stubbed Prometheus,
counting openings rather than asserting on a predicate string:

```
$ .venv/bin/python -m pytest apps/core/tests/test_detection.py -q
......                                                                   [100%]
6 passed in 0.08s
```

The e2e holds error_spike past detection for 60 more seconds, counts
incidents per pair over the window, then re-injects after the rate()[1m]
window has rolled off to prove a second episode still opens its own
incident:

```
$ MOCK_LLM=1 .venv/bin/python -m pytest e2e/test_detection_episodes.py -q
.                                                                        [100%]
1 passed in 198.36s (0:03:18)
```

What it looks like in the incident table. Before, from section 2 of this
report, one pair over six minutes of a fixture run:

```
error_rate/target-gateway: 47 incidents, 02:27:17.821Z .. 02:33:34.021Z
```

After, the same rule and service across the whole 19m05s fixture suite,
which injects error_spike four separate times: four incidents, one per
injection.

### Defect 5, a parked approval after a page reload

The Zustand store now seeds itself from REST on connect and on every
reconnect: `listIncidents`, filtered to the three non-terminal statuses,
then the full event log of each. `mergeSeed` drops anything the socket
already delivered by event id and puts the rest in front of the live
events, so an incident's own slice stays in seq order and the REST/WS
overlap folds identically either way. `ApprovalOverlays` is unchanged; it
selects the same events it always did, there are just events to select
now. The drawer also takes initial focus on mount and traps Tab, instead
of sitting at the end of the tab order behind the whole incident feed.

```
$ npx vitest run app/store/events.test.ts app/components/ApprovalDrawer.test.tsx
 Test Files  2 passed (2)
      Tests  10 passed (10)
```

The e2e parks a real red-tier action at a LangGraph `interrupt()`, waits
for the drawer to appear live, reloads the page, and approves from the
drawer the seed brings back. `/ws/events` still tails Redis from `$` with
no backfill, so nothing but the seed can put that drawer back:

```
$ MOCK_LLM=1 .venv/bin/python -m pytest e2e/test_approval_reload.py -q
.                                                                        [100%]
1 passed in 7.93s
```

The assertions after the click read the event log, not the screen: the
approval is signed by a `human:` actor, carries the seeded action id, is
followed by `action.executed`, and the chain still verifies. The drawer's
own "approved, signed <fingerprint>" line is deliberately not what the
test waits on; section 5 of this report measured it on screen for about a
second, so the stable signal is the drawer unmounting.

### Defect 6, the forced 3D scene under reduced motion

`Topology3D` reads `useReducedMotion()` and passes it down as `still`.
The frameloop collapses to `demand` even with an incident active, the
5fps `IdleTicker` never starts, the edge dash offset holds, the agent orb
parks at a fixed point on its orbit instead of circling it, the node
flash is skipped and the camera jumps to its resting pose in one frame.
Frames are then only drawn when the topology state actually changes.

```
$ MOCK_LLM=1 .venv/bin/python -m pytest e2e/test_reduced_motion.py -q
.                                                                        [100%]
1 passed in 18.36s
```

The check is three parts: reduced motion with no override still lands on
the 2D renderer with zero running Web Animations; `?view=3d` under
reduced motion produces byte-identical canvas screenshots across a 4s
idle gap; and a control run of the same scene with no preference set
produces different ones. Without the control, "identical pixels" would
also be what a canvas that failed to render at all produces.

### What the episode rule changed in the suite

The first full re-run came back 16/18. `test_latency_heals` waited 90s
for an incident that was never going to open:

```
E       TimeoutError: no incident for latency_p95/target-orders within 90s
FAILED e2e/test_reduced_motion.py::test_forced_3d_holds_still_under_reduced_motion
FAILED e2e/test_scenarios.py::test_latency_heals - TimeoutError: no incident ...
2 failed, 16 passed in 904.34s (0:15:04)
```

Both failures are the suite's own ordering, and both are worth recording
because they are the cost of the amended rule rather than bugs in it.
`test_evidence_pack` injects latency, heals it and clears the toxic at
05:23:1x; `test_latency_heals` re-injects 20s later. p95 never dipped
below threshold in between, so by plan/03's wording that is one continuous
firing episode and the second injection correctly shares the first
incident. The reduced-motion check failed for the neighbouring reason:
`latency_p95` on target-gateway was still resolving while it sampled, and
a running incident repaints the scene for real reasons.

Fixed in the tests, not in the rule. An autouse fixture waits for both
threshold rules to read clean before each test, using detection's own
rules.yaml and `query_prometheus` from inside core-api rather than a
second copy of the PromQL, and the reduced-motion check additionally waits
for no incident to be in flight. The pair that failed, run back to back:

```
$ MOCK_LLM=1 .venv/bin/python -m pytest e2e/test_evidence_pack.py e2e/test_scenarios.py::test_latency_heals -q
..
2 passed in 142.54s (0:02:22)
```

### Full re-verify

```
### make lint test 2026-08-07T06:17:57Z
All checks passed!                            (ruff)
Success: no issues found in 51 source files   (mypy)
53 passed, 2 warnings in 0.77s                (pytest apps/core)
 Test Files  8 passed (8)
      Tests  46 passed (46)                   (vitest, console)
PASS: 9/9                                     (opa test)
### exit=0
```

apps/core goes from 47 tests to 53 and the console from 36 to 46.

```
### fixture e2e start 2026-08-07T05:36:00Z
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest e2e -q
..................                                                       [100%]
18 passed in 1145.13s (0:19:05)
### fixture e2e end 2026-08-07T05:55:08Z
```

`make e2e` now installs the Chromium binary first (Makefile, `browsers`
target), because two of the three new tests only exist in a browser and
the pip wheel carries no browser. Same reasoning as the `make venv` gap
the stranger test found in section 2: a clean clone must not collect tests
it cannot run. CI gets one added step for the shared libraries, which are
the only part needing root.

### Live e2e: still not a clean run, and this time the budget was gone first

```
### live e2e start 2026-08-07T05:56:07Z LLM_LARGE=llama-3.3-70b-versatile
MOCK_LLM=0 .venv/bin/python -m pytest e2e -q
FAILED e2e/test_approvals.py::test_veto_during_the_window_escalates_instead_of_healing
FAILED e2e/test_checkpoint_resume.py::test_killing_worker_mid_run_resumes_from_checkpoint
FAILED e2e/test_scenarios.py::test_latency_heals - AssertionError: {'id': 'in...
FAILED e2e/test_scenarios.py::test_crash_heals - AssertionError: {'id': 'inc_...
FAILED e2e/test_scenarios.py::test_error_spike_heals - AssertionError: {'id':...
FAILED e2e/test_scenarios.py::test_memory_leak_heals - AssertionError: {'id':...
FAILED e2e/test_scenarios.py::test_cache_outage_heals - AssertionError: {'id'...
7 failed, 11 passed in 1199.86s (0:19:59)
### live e2e end 2026-08-07T06:16:10Z
```

Every failure is the same 429, and the counter inside it is the point:

```
on tokens per day (TPD): Limit 100000, Used 99658
```

99,658 of 100,000 were already spent when this run started. The key is
the second one, the one section 3 introduced fresh at 04:06Z and then
spent 135,069 tokens on inside nine minutes. Tokens on this stack's
`agent_runs` rows, split at the moment `make e2e-live` started:

```
this live run : {'ti': 15151, 'tout': 1034, 'n': 22}      (16,185 tokens)
earlier today : {'ti': 277153, 'tout': 21726, 'n': 2093}  (298,879 tokens)
```

So this pass could not test the prediction it was meant to test. The
brief's instruction for exactly this case was to stop and report rather
than substitute a model, and no model was substituted:
`LLM_LARGE=llama-3.3-70b-versatile` throughout, the committed default.

What the run does measure is volume, because a 429 escalation is the same
shape of failure the storm fed on: an incident that dies immediately while
its fault keeps firing. Section 3's pre-fix run, nine minutes, 60
incidents opened, 49 escalated. This run, twice as long, with 23 of 30
incidents escalating on 429:

```
incidents opened during the 19m59s live run: 30
    8  ('error_rate', ('target-gateway',), 'escalated')
    7  ('synthetic', (), 'resolved')
    5  ('error_rate', ('target-payments',), 'escalated')
    3  ('latency_p95', ('target-orders',), 'escalated')
    3  ('latency_p95', ('target-gateway',), 'escalated')
    3  ('service_down', ('target-payments',), 'escalated')
    1  ('error_rate', ('target-orders',), 'escalated')

escalated: 23  resolved: 7
live run agent runs: {'ti': 28013, 'tout': 1926, 'cost': 0.00662, 'n': 59}
```

Read those repeats carefully: they are one per injection, not one per
poll. Eight `error_rate` incidents on target-gateway across twenty minutes
are eight separate faults injected by different tests, each after the
metric had decayed clean; the pre-fix run's 19 came from a single fault
re-opening every five seconds. 59 agent runs against the pre-fix run's
157, over twice the wall clock.

That is consistent with section 3's prediction that fixing defect 3 puts
the suite inside a free-tier day, and it is not a confirmation of it. A
clean `make e2e-live` still needs a key with an unspent daily budget.

### README numbers: not refreshed, and why

Step 5 of the phase 7 brief asks for three fresh samples each of
error_spike and cache_outage from `scripts/collect_live_numbers.py`, to
replace the two rows section 3 left unchecked. That needs the same live
budget the suite just failed on, so it was not run and no number in the
README moved. The table still carries the phase 6 measurements and its
`cache_outage (n=1)` caveat, which remain the last real runs behind them.
`collect_live_numbers.py` did gain a `--scenarios` flag so the top-up is a
two-scenario run rather than a fifteen-run one when a budget exists.

The one part of step 5 that needed no tokens was done. The README's
quickstart wording, read off the running chaos screen rather than the
source:

```
card title text : 'LATENCY'
card title css  : uppercase
button label    : 'inject fault'
cards on screen : 5
all button texts: ['inject fault', 'inject fault', 'inject fault', 'inject fault', 'inject fault']
```

The README says press **inject fault** on the **latency** card, which is
what is on screen (the card's source text is `latency`; the capitals are
CSS). Defect 1 stays closed.

### State this addendum leaves behind

- Branch `phase-7` off `phase-6`, tagged `phase-7`. Nothing pushed, no
  remote touched, `v0.1.0` not tagged. The release decision is still the
  reviewer's, and one of its inputs, a clean `make e2e-live`, is still
  unmeasured.
- `.env` back to `MOCK_LLM=1` and the committed default model, never
  staged, verified against `.env.example`:

```
$ diff <(redact .env) <(redact .env.example)
identical to .env.example apart from the redacted secret
```

- The stack is up in fixture mode. `make down` clears it, including the
  incident rows this pass generated.
- No separate `docs/reports/PHASE_7_REPORT.md` exists: the phase 7 brief
  names this addendum as the phase report. `scripts/gate.sh 7` would fail
  its report-exists check for that reason, and was not run.

## Live verification

Run on 2026-08-07 on branch `phase-7`, on a third Groq key with an
untouched daily budget, `LLM_LARGE` left at the committed
`llama-3.3-70b-versatile`. Budget confirmed before anything was spent on
it, and the stack recreated so the containers picked the key up:

```
HTTP/2 200
x-ratelimit-limit-requests: 1000
x-ratelimit-remaining-requests: 999

MOCK_LLM=0
LLM_LARGE=llama-3.3-70b-versatile
```

### The suite

```
### live e2e start 2026-08-07T06:30:38Z LLM_LARGE=llama-3.3-70b-versatile
MOCK_LLM=0 .venv/bin/python -m pytest e2e -q
FAILED e2e/test_approvals.py::test_veto_during_the_window_escalates_instead_of_healing
FAILED e2e/test_scenarios.py::test_latency_heals - AssertionError: ['restart_...
FAILED e2e/test_scenarios.py::test_error_spike_heals - AssertionError: {'id':...
FAILED e2e/test_scenarios.py::test_cache_outage_heals - TimeoutError: no inci...
4 failed, 14 passed in 1142.72s (0:19:02)
### live e2e end 2026-08-07T07:04:49Z
```

14 of 18, against 10 of 15 on the pre-fix run in section 3. Not the 18/18
this pass was aiming at. The thing that changed is why: not one failure is
a rate limit. Over the whole run the worker log holds zero of them, the
single grep hit being a millisecond in a timestamp:

```
$ docker logs aegis-core-worker-1 | grep 429
2026-08-07 06:48:05,429 worker HTTP Request: GET http://target-orders:9001/healthz "HTTP/1.1 200 OK"
$ docker logs aegis-core-worker-1 | grep -c "Rate limit"
0
```

### Defect 3's prediction: confirmed, with 3.4% to spare

Section 3 predicted that fixing defect 3 was "very likely enough to make
`make e2e-live` pass on a free-tier key". On the question it was actually
about, the day's token budget, it holds. The suite ran start to finish
without hitting the limit once:

```
agent runs: 84, tokens_in 91422, tokens_out 5153, total 96575, cost $0.0432
  escalated   14 incidents    49324 tokens
  resolved    16 incidents    49134 tokens
```

Against the pre-fix run: 157 agent runs and 135,069 tokens in 9m05s, which
blew through the 100,000 daily limit before the suite was half done. This
run did twice the wall clock on 96,575 tokens and 84 runs.

Confirmed, then, and worth saying exactly how narrowly: **96,575 of
100,000 is 3.4% of a free-tier day left over.** The prediction was that
the storm was what put the suite over the line, and removing it does bring
the suite back under, but there is no room in that budget for a second run
or for the follow-up collection this pass also wanted. A repeat on the
same key on the same day would 429.

The incident volume behind those numbers, one row per (rule, service,
status):

```
incidents opened during the 19m02s live run: 30
   16 resolved, 14 escalated
```

The 14 escalations still cost half the budget (49,324 tokens), but they
are a different animal from defect 3's: each is a distinct fault, escalated
once on the model's own judgement, not one fault re-opening every five
seconds. Sixteen incidents resolved end to end against real model calls,
including six that healed autonomously in 34s or less.

### The four failures, none of them quota

**`test_latency_heals`**, the most interesting one. The live diagnose agent
blamed redis rather than the injected Toxiproxy latency, and
plan_remediation proposed `restart_dependency` on redis (yellow tier)
instead of `remove_toxic` (green). Policy allowed it, the 30s veto window
opened and timed out unvetoed, the action executed, verify passed and the
incident resolved auto in 34s:

```
  action restart_dependency   tier=yellow  status=executed  conf=0.80  policy=True (allow_yellow_tier)
  06:43:28.942 action.proposed           {'tier': 'yellow', 'params': {'service': 'redis'}, ...}
  06:43:28.978 action.veto_window_opened {'closes_at': '2026-08-07T06:43:58.978Z'}
  06:43:59.434 action.executed           {'result': {'action': 'restart', 'container': 'redis'}}
  06:44:00.020 verify.passed
  06:44:00.024 incident.resolved         {'autonomy': 'auto', 'mttr_seconds': 34}
```

The test asserts the exact catalog key, so it fails on the action's
identity, not on whether the incident healed. Two things in that trace
deserve the reviewer's attention rather than a fix slipped in here. Verify
passed while the injected toxic was still in place, so the probes called
a system healthy that the test had not yet un-broken. And
`restart_dependency` on redis restarts the same container AEGIS uses for
its own event stream, which is what produced the `failed to publish event`
lines later in the run.

**`test_error_spike_heals`**. Both the payments incident and its collateral
gateway one escalated with `gate allowed no proposed action`:
plan_remediation returned no action at all for an error-rate fault. Nothing
was denied and nothing crashed, the agent simply proposed nothing.

**`test_veto_during_the_window_escalates_instead_of_healing`**. The same
scenario needs a yellow action to exist so it can be vetoed. Live, diagnose
came back with confidence 0.0 and proposed `remove_toxic` for an error-rate
fault, and OPA denied it on `deny_low_confidence`, so no veto window ever
opened and the test timed out waiting for one:

```
  action remove_toxic   tier=green  status=denied  conf=0.0  policy=False (deny_low_confidence)
  06:33:09.233 action.policy_checked  {'decision': 'deny', 'opa_rule_id': 'deny_low_confidence'}
  06:33:09.235 incident.escalated     {'reason': 'OPA denied remove_toxic (...)'}
```

Policy did its job here. The confidence gate is exactly what should stop a
zero-confidence action, and the test's assumption that a yellow action will
be available to veto is what did not survive contact with a live model.

**`test_cache_outage_heals`**, and a stall this pass could not explain.
The test injected at 06:48:35 and timed out at 06:50:05 with
`no incident for latency_p95/target-orders within 90s`. An incident for
exactly that pair did open at 06:49:38, inside the window, so the timeout
and the incident table disagree and this report is not going to guess which
one is wrong. What is certain is that the run stalled hard around that
moment. The worker log goes silent for fifteen minutes:

```
2026-08-07 06:49:28,242 worker failed to publish event 01KZDFQPEWSRBQF67VP943ZJ7C to redis stream:
2026-08-07 06:49:40,383 worker incident inc_01KZDFR2A8GFXXEV3NGYZTK2S3 opened: latency_p95 on target-orders
2026-08-07 06:49:52,286 worker HTTP Request: POST http://opa:8181/v1/data/aegis/actions/decision "HTTP/1.1 200 OK"
2026-08-07 07:05:25,848 worker HTTP Request: POST http://core-executor:8090/execute "HTTP/1.1 200 OK"
2026-08-07 07:05:25,871 worker failed to publish event 01KZDGMZK4K7B9AJ39PVXYTD6H to redis stream: Connection closed by server.
```

The suite's own wall clock matches: its last test should have ended around
06:50:10 and it exited at 07:04:49. Two incidents from that window carry
the damage in their MTTR, a 30s veto window that took 947s and 3893s to
reach `action.executed`:

```
06:49:26 latency_p95 target-gateway  resolved  mttr=3893  auto
06:49:38 latency_p95 target-orders   resolved  mttr=947   auto
```

Both eventually healed, one of them an hour after the suite had given up on
it. The `failed to publish` lines point at Redis, which the run had already
restarted once via `restart_dependency` and restarted again at 07:54 when
the second of these finally executed. Whether the stall is Redis, the
Docker daemon under a 94%-full disk, or the coupling between them is not
something this pass established, and it is a new observation rather than
one of the seven defects.

### What was not run, and why

Steps 2 and 3 of this pass, three fresh `collect_live_numbers.py` samples
each of error_spike and cache_outage and the README table update that
depends on them, were not run. Six incidents at the ~3,070 tokens a
resolved incident cost in this run is roughly 18,000 tokens, against the
3,425 the day had left after the suite. Attempting it would have produced
half a table and a 429, so **no number in the README moved** and the
`cache_outage (n=1)` caveat stays. The remaining rows were not re-checked
against the 20% band either, for the same reason: there is nothing new to
check them against.

That leaves one item genuinely outstanding for the release decision. A
clean `make e2e-live` is now a question about three live agent behaviours,
not about money, and the README's error_spike and cache_outage rows are
still carrying their phase 6 samples.

### State this section leaves behind

- Branch `phase-7`, tagged `phase-8` on this commit. Nothing pushed, no
  remote touched, `v0.1.0` not tagged.
- `.env` back to `MOCK_LLM=1` and the committed default model, never
  staged, verified against `.env.example`:

```
$ diff <(redact .env) <(redact .env.example)
identical to .env.example apart from the redacted secret
```

- `.env` holds the third key, since the first two are spent. Its daily
  budget is spent too as of this run.
- The stack is up in fixture mode. `make down` clears it, including the
  30 incident rows this run generated.

## Phase 9

Run on 2026-08-07, branch `phase-9` off `phase-7`, same machine and stack as
the rest of this report. Phase 9 splits the Redis instances, hardens three
tests against live model variance, and makes a passing verification say
whether the injected fault was still there. Every command output below is
pasted from the run.

The fixture suite passes 18/18. The live suite reaches 17 of 18, against 14
of 18 in phase 8, and the one failure is `test_latency_heals` failing on the
new assertion for the right reason: the incident healed while the fault that
caused it was still in place. That is recorded and left alone, per the
brief. The first attempt at this pass, a day earlier, produced nothing
usable because the machine could not keep a database up; that is set out in
"The machine, and the day it cost".

### What changed

| Commit    | What                                                                                              |
| --------- | ------------------------------------------------------------------------------------------------- |
| `90a06cf` | Two Redis containers, `shop-redis` and `aegis-redis`, plus the executor's container guard         |
| `4d84ada` | verify records whether the injected fault survived, in the event payload and the incident summary |
| `ab2c4e1` | Scenario tests assert the fault is gone instead of asserting one catalog_key                      |
| `d8328ea` | The veto test seeds its own yellow action instead of waiting for a model to propose one           |
| `23177cf` | plan_remediation's prompt names all eight catalog keys and forbids an empty plan                  |
| `050dc89` | Prettier on the two files the above touched                                                       |

### The Redis split

plan/01's runtime topology table was amended before the code: one `redis`
row becomes `shop-redis` (demo cache, the only Redis a catalog action may
name) and `aegis-redis` (event stream, in no catalog action at all).
`restart_dependency`'s enum goes from `[redis, toxiproxy]` to
`[shop-redis, toxiproxy]`, and `cache_outage` pauses `shop-redis`.

The point of the split, checked against the running stack: pausing the shop
cache leaves the event bus running, so the incident the outage causes can
still be published while the fault is in place.

```
$ curl -s -X POST http://localhost:8080/api/chaos/cache_outage > /dev/null
$ curl -s http://localhost:8080/api/chaos/cache_outage
{"scenario":"cache_outage","fault_present":true}
$ docker inspect -f '{{.State.Status}}' aegis-redis
running
$ curl -s -X DELETE http://localhost:8080/api/chaos/cache_outage > /dev/null
$ curl -s http://localhost:8080/api/chaos/cache_outage
{"scenario":"cache_outage","fault_present":false}
```

Behind the enum, `aegis.actions.execute.guard_container` runs on every path
in `run()` that reaches `docker_ops` and rejects any container outside the
demo set. The catalog and OPA both already constrain the name; neither of
them sits between the executor and the Docker socket, and this does. The
unit tests cover the guard directly, `run()` with `docker_ops` patched to
raise if it is called at all, and the membership of `DEMO_CONTAINERS`
itself, so an `aegis-*` name added to that set by a later edit fails a test
rather than quietly reopening the hole.

```
$ .venv/bin/python -m pytest apps/core/tests/test_catalog.py -q
............................                                             [100%]
28 passed in 2.48s
```

The gotcha in the brief was to give the two containers distinct hostnames
everywhere rather than aliasing one to the other. `REDIS_URL` is gone,
replaced by `SHOP_REDIS_URL` and `AEGIS_REDIS_URL`, and every remaining
`redis:6379` in the repo is now one of those two explicit hostnames:

```
$ grep -rn "redis:6379" . | grep -v node_modules | grep -v '\.venv' | grep -v '^\./\.git/'
.env.example:18:SHOP_REDIS_URL=redis://shop-redis:6379/0
.env.example:21:AEGIS_REDIS_URL=redis://aegis-redis:6379/0
plan/phases/phase-9.md:31:- The two Redis containers need distinct hostnames everywhere ...
apps/core/aegis/actions/execute.py:21:SHOP_REDIS_URL = os.environ.get("SHOP_REDIS_URL", "redis://shop-redis:6379/0")
```

### Whether the fault survived verification

The phase 8 live run had `test_latency_heals` verify green and resolve in
34s with the Toxiproxy toxic still installed. The probes were not wrong,
they were answering a narrower question than a reader assumes. verify now
asks the chaos API whether the originally injected fault is still there and
puts the answer in the `verify.passed` / `verify.failed` payload as
`injected_fault_present`: true, false, or null when the question cannot be
answered. A pass with the fault still in place also appends a marker to
`incidents.summary`, so it shows up in the incident list rather than only in
a container log.

Three things this deliberately does not do. It does not change the probe
logic, which the brief put out of scope. It does not change routing, since
`passed` still decides resolve against rollback. And it never reaches a
prompt: the signal is written to the database and the event log, never back
onto `state["incident"]`, so no later node can read it as evidence. A chaos
API that cannot answer returns null rather than an optimistic false.

`GET /chaos/{scenario}` is a new route, added to plan/02's table in the same
commit and flagged here. `target-payments` grew a `GET /internal/fault` to
read back the two toggles it already accepted writes for. Neither is on an
agent path.

### The three tests, and what they now prove

`test_latency_heals` and the other four scenario tests asserted one exact
catalog_key. That checks which route the model picked, not whether the
system healed, and it fails in both directions: the phase 8 run failed on
the action's identity while the incident had genuinely resolved (with the
fault still live, which the old assertion caught only by accident), and a
correct heal reached by another legal catalog_key would have failed for no
reason at all. The assertion is now that the incident resolved, that at
least one action executed, and that `GET /chaos/{scenario}` reports the
fault gone. `fault_present` must be false; null fails too, because an
unanswerable chaos API proves nothing. That is strictly harder to satisfy
than what it replaced.

`test_veto_during_the_window_escalates_instead_of_healing` needed a live
model to produce a confident yellow action before it could begin. In the
phase 8 run the model returned a green `remove_toxic` at confidence 0.0 for
an error-rate fault, OPA denied it on `deny_low_confidence`, no window
opened, and the test timed out on a policy engine doing its job.
`scripts/seed_yellow_action.py` now seeds `rollback_config` on
target-payments, the action plan/03's chaos table expects error_spike to
produce, and runs a real gate node so a real 30 second window opens. Same
technique as the red-tier tests, for the same reason. The seed keeps the
live `gate_router`, so a veto that fails to land routes to execute and the
"nothing executed" assertion fails as it should.

The adversarial, approval, chain, evidence pack and reduced-motion tests are
untouched, as the brief required.

### The prompt iteration

Both error_spike incidents in the phase 8 live run escalated with "gate
allowed no proposed action": plan_remediation returned no action at all for
an error-rate fault. The prompt pointed at `get_catalog` for the key list,
putting the eight keys one tool call away rather than on the page, and never
said that an empty plan is not an answer. Both are fixed: the keys are in a
table with the condition each one suits, the error-rate case maps explicitly
to `rollback_config`, and the output section requires 1 or 2 entries with
instructions to name the closest key at low confidence rather than nothing.
Policy still decides what runs. One iteration, no model swap.

### make lint test

```
$ make lint test
ruff:     All checks passed!
mypy:     Success: no issues found in 51 source files
eslint:   (clean, both workspaces)
prettier: All matched files use Prettier code style!
pytest:   84 passed, 2 warnings in 12.73s
opa:      PASS: 9/9
```

84 unit tests against phase 7's 74: the ten new ones are the container
guard, the catalog enum, `chaos.base_scenario` and the chaos status route.

### The machine, and the day it cost

The first attempt at this pass, on 2026-08-07, never produced a valid run.
Both Postgres containers crash-looped under I/O starvation with the volume
at 94% (12Gi free), `fsync` of a data directory taking 10 to 32 seconds:

```
10:53:24 [1] LOG:  server process (PID 1389) exited with exit code 2
10:53:30 [1] LOG:  all server processes terminated; reinitializing
10:56:24 [1515] LOG: syncing data directory (fsync), elapsed time: 20.17 s
psycopg.OperationalError: consuming input failed: server closed the connection unexpectedly
```

One fixture attempt opened 60 incidents and escalated 60, resolving none.
It was killed rather than reported, because it measured the disk. A later
`make up` failed outright on `container shop-db is unhealthy`
(`FailingStreak=16`). Three rounds of Docker pruning and a daemon restart
did not hold: each prune freed space that the rebuild it forced consumed
again, 29Gi back to 20Gi in a single `make up`. Docker held about 8GB in
total, so pruning it was the wrong lever, and the entry above about the
`snapshotter.Usage` error and the 1.4 to 2.2 second `healthz` is the
signature to check for next time.

Freeing non-Docker disk is what fixed it. At 33Gi free (82%) the whole
stack came up healthy in 21 seconds:

```
$ curl -s -o /dev/null -w "%{time_total}\n" http://localhost:8080/healthz
0.002364
0.001635
0.001691
$ docker logs aegis-aegis-db-1 | grep -c "all server processes terminated"
0
```

Milliseconds against seconds, and zero database restarts across both suites
that followed. Every number below was measured on that stack.

### Fixture e2e: 18/18

```
### fixture e2e 2026-08-07
MOCK_LLM=1 .venv/bin/python -m pytest e2e -q
..................                                                       [100%]
18 passed in 1020.18s (0:17:00)
```

The new `injected_fault_present` signal on every heal in that run:

```
latency_p95  mttr= 41s verify.passed  injected_fault_present=False
latency_p95  mttr= 55s verify.passed  injected_fault_present=False
service_down mttr=  7s verify.passed  injected_fault_present=False
error_rate   mttr= 81s verify.passed  injected_fault_present=False
service_down mttr=  6s verify.passed  injected_fault_present=False
```

### Live e2e: 17/18, and the one failure is the point

`.env` was switched to `MOCK_LLM=0` and the containers recreated, since the
worker reads that variable from the file rather than from the make
invocation. Confirmed before starting, because a live run that silently
serves fixtures proves nothing:

```
$ docker exec aegis-core-worker-1 printenv MOCK_LLM
0
```

```
### live e2e start 2026-08-07T19:47:07Z LLM_LARGE=llama-3.3-70b-versatile
MOCK_LLM=0 .venv/bin/python -m pytest e2e -q
FAILED e2e/test_scenarios.py::test_latency_heals - AssertionError: latency: i...
1 failed, 17 passed in 1188.39s (0:19:48)
### live e2e end 2026-08-07T20:06:58Z
```

17 of 18, against 14 of 18 in the phase 8 run. The three tests phase 9 set
out to make survive live model variance all pass:
`test_error_spike_heals`, `test_cache_outage_heals` and
`test_veto_during_the_window_escalates_instead_of_healing`. The prompt
iteration held, since no incident escalated with "gate allowed no proposed
action" this time.

The failure is `test_latency_heals`, and it is the same live model
behaviour as phase 8 caught for a better reason:

```
AssertionError: latency: incident inc_01KZEWWT9R5E8KDEBWVSR0ZABZ resolved but
fault_present=True after actions ['restart_dependency']
```

The trace, with the injected Toxiproxy toxic still installed throughout:

```
19:58:39.931  incident.detected     latency_p95 target-orders  p95=4458.33ms
19:58:43.202  action.proposed       restart_dependency tier=yellow params={'service': 'shop-redis'} conf=0.8
19:58:43.236  action.policy_checked allow rule=allow_yellow_tier
19:58:43.237  action.veto_window_opened  closes_at 19:59:13.237Z
19:59:13.919  action.executed       restart_dependency -> {'action': 'restart', 'container': 'shop-redis'}
19:59:14.291  verify.passed         injected_fault_present=True
19:59:14.294  incident.resolved     mttr=34s autonomy=auto
```

Every component did its job. Detection fired on real latency, triage
classified it, policy allowed a legal yellow action, the veto window opened
and timed out unvetoed, the executor restarted exactly the container it was
asked to, and the probes found a healthy system because restarting the cache
did clear the symptom. The diagnosis was wrong: 1500ms of Toxiproxy latency
between target-orders and its database is not a cache fault, and
`remove_toxic` was the green action that would have removed it.

What phase 9 changed is that this is now recorded rather than trusted. The
same thing happened in phase 8 at the same 34 second MTTR, and the report
could only note it after reading a container log by hand. This run wrote it
into the hash-chained event log at the moment of the verdict, and onto the
incident itself:

```
$ curl -s .../api/incidents/inc_01KZEWWT9R5E8KDEBWVSR0ZABZ
status  : resolved | mttr 34 | autonomy auto
summary : p95 latency on target-orders is 4458.33ms, exceeding the threshold
          of 1000ms. [injected fault still present at verify]
```

A reader scanning the incident list sees the marker. A reader opening the
timeline sees `injected_fault_present=True` next to `verify.passed`. The old
assertion would have failed this run too, but on the action's identity,
which is the right verdict for the wrong reason and would equally have
failed a correct heal that took another legal route.

Per the phase 9 brief, this is recorded and left alone: it fails on live
model quality, not infrastructure, so no model was substituted and no
assertion was loosened to make it pass.

### Cost, and a correction to the phase 8 budget arithmetic

```
agent runs: 87, tokens_in 101456, tokens_out 6246, total 107702, cost $0.04792
incidents opened during the live run: 29
   21 resolved, 8 escalated
resolved: 21, avg mttr 31s, fastest 2s
```

```
$ docker logs aegis-core-worker-1 | grep -c "Rate limit"
0
```

107,702 tokens and not one 429, which the phase 8 report would have called
impossible against a 100,000 per day limit. That report was wrong on one
point: the limit is per model, not per key. Split by model:

| Model                   | Runs | Tokens | Share of its own 100,000 |
| ----------------------- | ---- | ------ | ------------------------ |
| llama-3.3-70b-versatile | 44   | 76,942 | 77%                      |
| llama-3.1-8b-instant    | 43   | 30,760 | 31%                      |

Phase 8 measured 96,575 across both models, read it against a single cap and
concluded there was 3.4% of the day left. The real figure was the large
model's share, and there was more room than it thought. Its conclusion about
defect 3 stands, since the storm was real and removing it did bring the
suite under; only the headroom arithmetic was off. The suite costs about
77,000 large-model tokens, so two runs a day on one key is the real ceiling,
not one.

### collect_live_numbers: gated, not run

The brief gates the three-sample collection and the README table update on
the live suite passing. At 17 of 18 it did not, so neither ran, no number in
the README moved, and the `cache_outage (n=1)` caveat stays. This is a
deliberate stop, not a budget problem: the large model had 23,000 tokens of
its day left, which is enough for the roughly 18,000 the collection needs.

### Defect table

| #   | Severity | What                                                                                                                                                  | Status                    |
| --- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| 8   | high     | One Redis served both the shop cache and the event stream, so `restart_dependency` could restart AEGIS's own event bus mid-incident                   | fixed (phase 9)           |
| 9   | medium   | verify could pass, and an incident resolve, with the injected fault still in place, visible only in a container log                                   | fixed (phase 9)           |
| 10  | medium   | Three e2e tests failed on live model variance rather than on behaviour                                                                                | fixed (phase 9), 3/3 live |
| 11  | medium   | plan_remediation proposed no action at all for an error-rate fault                                                                                    | fixed (phase 9), live     |
| 12  | high     | The stack could not stay up: both Postgres containers crash-looped under I/O starvation and `make up` failed                                          | fixed, disk freed         |
| 13  | medium   | Live diagnose reads Toxiproxy database latency as a cache fault, so `latency` heals with `restart_dependency` and the toxic survives a passing verify | open, live model quality  |

Defect 13 is what stands between this branch and 18/18. It is a diagnosis
quality problem, not a safety one: the wrong action was legal, reversible,
policy-approved and openly recorded, and the run that took it is now
labelled as having left its fault in place. The brief allowed one prompt
iteration this pass and it was spent on plan_remediation, which the live run
confirms worked.

### State this section leaves behind

- Branch `phase-9`, tagged `phase-9`. Nothing pushed, no remote touched,
  `v0.1.0` not tagged.
- `.env` back to `MOCK_LLM=1` and the committed default model, never staged,
  structurally identical to `.env.example`. It carries `SHOP_REDIS_URL` and
  `AEGIS_REDIS_URL` in place of `REDIS_URL`.
- The stack is up in fixture mode. `make down` clears it, including the 29
  incident rows the live run generated.
- Outstanding for the release decision: defect 13, and behind it the
  three-sample collection and the README table update that the brief gates
  on a clean live suite.

## Phase 10

Run on 2026-08-08, branch `phase-10` off `phase-9`, same machine and stack.
Phase 10 spent its one scoped attempt at defect 13 on the evidence layer:
`query_traces` now finds slow traces and times each dependency call inside
them, and the diagnose prompt requires the hypothesis to rest on a tool
output the model actually read. The fixture suite passes 18/18 with both
changes in.

The live suite did not test them. It reached 13 of 18, and all five
failures are the same 429: the large model's daily token budget was
already at roughly 92,000 of 100,000 when the run started, held by phase
9's suite seven hours earlier. Every `latency` incident escalated before
diagnose made one tool call. The three-sample collection the brief made
unconditional hit the same wall on its first incident and was stopped.
Defect 13 is therefore neither confirmed fixed nor confirmed open by this
pass, and it is recorded that way below.

### What changed

| Commit    | What                                                                    |
| --------- | ----------------------------------------------------------------------- |
| `498b6c8` | `query_traces` searches for slow traces and times each dependency call  |
| `2a278c8` | diagnose prompt: three evidence rules, and traces before naming a cause |

### The tool was the larger half of defect 13

The phase 9 trace reads as a reasoning failure: the model blamed the cache
for latency that sat between orders and its database, with the
distinguishing evidence "available and apparently unused". Checking what
the tool actually returned changes that reading. `query_traces` asked
Tempo for the 20 most recent traces tagged with the service and reported
three fields per trace: id, root service, duration. Two things follow.

A tag search returns recent traces, not slow ones. With the 1500ms toxic
installed and every checkout through target-orders taking three seconds,
the tool came back with this:

```
$ curl -s -X POST http://localhost:8080/api/chaos/latency
$ docker exec target-gateway python -c "...POST /orders x3..."
3058.8 ms 200
3058.4 ms 200
3046.5 ms 200
$ # what the old query_traces(target-orders) returned at that moment
  {"trace_id": "...", "root_service": "target-gateway", "duration_ms": 34}
  {"trace_id": "...", "root_service": "target-gateway", "duration_ms": 71}
  {"trace_id": "...", "root_service": "target-gateway", "duration_ms": 11}
```

Requests were taking three seconds and the tool was reporting 34ms. The
slow traces existed the whole time; TraceQL finds them directly:

```
$ q='{ resource.service.name = "target-orders" && duration > 500ms }'
3091 <root span not yet received>
6150 target-gateway
1504 <root span not yet received>
3007 target-orders
```

And a trace duration never says what the request waited on. So the tool now
opens the slowest three and reports, per trace, the slowest call made to
each dependency, with the service that made it and what it called. Against
the live stack with the toxic in:

```
{
  "searched": "traces from target-orders slower than 500ms",
  "traces": [
    {
      "trace_id": "50f9bba3526a5dc3a139e57740d47881",
      "duration_ms": 10581,
      "slowest_call_per_dependency": [
        {"service": "target-gateway", "span": "POST",   "calls": "http target-orders:9001",     "duration_ms": 5013.37},
        {"service": "target-orders",  "span": "INSERT", "calls": "postgresql toxiproxy:5432",   "duration_ms": 3012.90},
        {"service": "target-orders",  "span": "SET",    "calls": "redis shop-redis:6379",       "duration_ms": 0.47}
      ]
    }
  ]
}
```

3012.90ms against 0.47ms, in one list, on the two dependencies the wrong
answer confused. One row per callee rather than the five slowest spans
outright: the slowest spans in a checkout trace are the HTTP spans that
contain all the others, and the first version of this fix returned
6225ms, 3055ms, 3050ms, 3038ms and 3037ms of enclosing spans while the
1.5s database call sat below the cut. Server spans carry their own
`http.url`, so only client spans are credited with calling anything.

Caps of 10 traces reported, 3 expanded, 5 calls each keep the result
inside the quarantine wrapper's 200-line budget (measured: 124 lines,
3564 characters under fault), and slowest-first ordering means a
truncation can only ever cost the fast tail.

### The prompt iteration

One iteration, on evidence rather than on the answer. Three rules: a claim
in the hypothesis has to be something a tool output in this run shows;
blaming a dependency means reading how long calls to it took first, and a
dependency answering in single-digit milliseconds is not the answer
however plausible it sounds; `evidence_refs` has to include the output the
hypothesis rests on. The workflow section keeps the cheap path for faults
that name themselves in logs and singles out slowness as the case metrics
cannot close.

The prompt does not mention the latency scenario, the toxic, Toxiproxy, or
the injection API. It never says which fault to expect. `net.peer.name` on
a database span happens to read `toxiproxy` because that is the hostname
orders connects through (plan/01's topology), and that string reaches the
model as quarantined tool data, not as prompt text.

The paused-cache route is unchanged in substance and now reached through
the same discipline: a slow call to the cache, or no completed spans at
all, then `get_container_stats("shop-redis")`.

### make lint test

```
$ make lint test
ruff:     All checks passed!
mypy:     Success: no issues found in 51 source files
eslint:   (clean, both workspaces)
prettier: All matched files use Prettier code style!
pytest:   88 passed, 2 warnings in 0.49s
vitest:   Test Files 8 passed (8), Tests 46 passed (46)
opa:      PASS: 9/9
```

88 unit tests against phase 9's 84. The four new ones cover the per-span
timings and their callees, the one-row-per-dependency rule, the fallback
when nothing is slower than the threshold, and degradation when Tempo will
not serve a trace body.

### Fixture e2e: 18/18 on the second attempt

The first attempt returned 17 of 18, on a stack that had been up for 100
seconds:

```
### fixture e2e start 2026-08-08T02:06:16Z
E       TimeoutError: no incident for error_rate/target-payments within 90s
FAILED e2e/test_adversarial.py::test_adversarial_log_line_never_yields_flush_queue
1 failed, 17 passed in 1061.57s (0:17:41)
```

That failure is upstream of anything this phase changed: it timed out
waiting for detection to open an incident, before any agent node ran. The
same test alone against the warm stack:

```
$ MOCK_LLM=1 .venv/bin/python -m pytest e2e/test_adversarial.py -q
.                                                                        [100%]
1 passed in 115.40s (0:01:55)
```

And the full suite, rerun on the warm stack:

```
### fixture e2e rerun start 2026-08-08T02:27:07Z
MOCK_LLM=1 .venv/bin/python -m pytest e2e -q
..................                                                       [100%]
18 passed in 1045.94s (0:17:25)
```

Fixtures replay by (incident, scenario, node) sequence index rather than
by prompt content, so the prompt change invalidated none of them and none
were re-recorded. Tools execute live in both modes, so the fixture runs did
exercise the new `query_traces` against real Tempo.

### Live e2e: 13/18, and none of the five failures is about diagnosis

`.env` was switched to `MOCK_LLM=0` and the containers recreated, and the
stack was given a three minute warm-up first, since the cold start is what
cost the adversarial test above:

```
$ docker exec aegis-core-worker-1 printenv MOCK_LLM LLM_LARGE
0
llama-3.3-70b-versatile
```

```
### live e2e start 2026-08-08T02:48:41Z LLM_LARGE=llama-3.3-70b-versatile
MOCK_LLM=0 .venv/bin/python -m pytest e2e -q
FAILED e2e/test_scenarios.py::test_latency_heals - AssertionError: {'id': 'in...
FAILED e2e/test_scenarios.py::test_crash_heals - AssertionError: {'id': 'inc_...
FAILED e2e/test_scenarios.py::test_error_spike_heals - AssertionError: {'id':...
FAILED e2e/test_scenarios.py::test_memory_leak_heals - AssertionError: {'id':...
FAILED e2e/test_scenarios.py::test_cache_outage_heals - AssertionError: {'id'}
5 failed, 13 passed in 1019.75s (0:16:59)
### live e2e end 2026-08-08T03:05:41Z
```

All five assert `status == 'resolved'` and got `escalated`. The reason is
identical on all five:

```
03:05:31.210 incident.detected     latency_p95 target-orders p95=7124.57ms
03:05:32.605 incident.classified   sev2
03:05:32.610 agent.run.started     diagnose llama-3.3-70b-versatile
03:05:39.860 agent.run.failed      429 tokens per day (TPD): Limit 100000, Used 99742
03:05:39.883 incident.escalated    reason: agent run crashed
```

Seven seconds from diagnose starting to diagnose dying, with no tool call
in between. 12 of the run's 14 escalations carry a 429 in their reason.
Every scenario failed the same way, which is itself the signal: a
diagnosis-quality problem does not take out `crash` and `memory_leak`
alongside `latency`.

### The budget was not fresh, and that is measurable

```
Rate limit reached for model `llama-3.3-70b-versatile` ... on tokens per
day (TPD): Limit 100000, Used 99742, Requested 1629. Please try again in
19m44.544s.
```

"Try again in 19m44s" is the tell: Groq's TPD is a rolling 24 hour window,
not a calendar-day reset. Phase 9's suite spent 76,942 large-model tokens
between 19:47Z and 20:07Z on 2026-08-07, and this run started at 02:48Z on
2026-08-08, about seven hours later. Those tokens were still on the
counter. What this run spent on its own:

```
model                   | runs | tokens_in | tokens_out | total | cost
llama-3.1-8b-instant    |  35  |   22335   |    1688    | 24023 | $0.00135
llama-3.3-70b-versatile |  29  |   22506   |     920    | 23426 | $0.01399
```

23,426 large-model tokens, and it still ran out, because it began with
roughly 8,000 of headroom and was fed only by what aged out of the window
mid-run. The phase 9 report's ceiling of "two runs a day on one key" holds
only if those two runs are more than 24 hours apart, not merely on
different dates. That correction is the durable finding of this pass.

### collect_live_numbers: attempted, and stopped on the same wall

The brief made the three-sample collection unconditional this phase, so it
was attempted rather than gated. A probe first accepted a 32,000 token
reservation, which read as headroom; it was not. The first incident of the
first scenario died the same way, and a probe taken immediately after gave
the real figure:

```
### collect_live_numbers start 2026-08-08T03:08:27Z
03:09:12.675 agent.run.failed   diagnose  429 ... tokens per day (TPD)
03:09:12.688 incident.escalated reason: agent run crashed

$ # 20,000-token reservation, immediately after
status 429
Limit 100000, Used 99555, Requested 20039
```

445 tokens of headroom against roughly 18,000 needed. The run was killed
rather than left to generate escalated rows that measure a quota, and both
chaos toggles were cleared:

```
$ curl -s http://localhost:8080/api/chaos/error_spike
{"scenario":"error_spike","fault_present":false}
$ curl -s http://localhost:8080/api/chaos/cache_outage
{"scenario":"cache_outage","fault_present":false}
```

So no number in the README's measured table moved, the
`cache_outage (n=1)` caveat stays, and the remaining rows were not
re-checked against the 20% band, for the third pass running and the same
reason each time. The bulk of the window frees around 19:47Z on
2026-08-08.

### README

The measured table is untouched, since nothing was re-measured. "What this
is not" gained a paragraph naming diagnosis quality as the honest weak
point: that on the free-tier model the latency scenario is read as a cache
fault roughly as often as not, that the action taken in that case is legal,
reversible and policy-gated, and that the incident carries
`[injected fault still present at verify]` in its summary with
`injected_fault_present` in the event log. That claim rests on the phase 8
and phase 9 runs; phase 10 added no sample either way, and the paragraph
does not pretend otherwise.

### Defect table

| #   | Severity | What                                                                                                                                                                 | Status                          |
| --- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| 13  | medium   | Live diagnose reads database latency as a cache fault, so `latency` heals with `restart_dependency` and the toxic survives a passing verify                          | open, untested this pass        |
| 14  | medium   | `query_traces` searched recent traces, not slow ones, and reported no per-span timings, so the evidence separating a slow database from a slow cache was unreachable | fixed (phase 10), fixtures only |
| 15  | low      | The phase 9 budget arithmetic read the token cap as per calendar day; it is a rolling 24 hour window, so two runs seven hours apart share one budget                 | recorded, no code change        |

Defect 13 stays open and its status changes from "live model quality" to
"untested this pass". The attempt was made and the evidence layer behind it
is measurably better, but the model never saw the new evidence, so nothing
here is a claim about whether it would have read it correctly. Defect 14 is
new, and it is the part of defect 13 that was never a reasoning problem:
the tool could not surface the timing the diagnosis needed. It is fixed and
covered by four unit tests and the fixture suite, and it has not been
exercised by a live model.

### State this section leaves behind

- Branch `phase-10`, tagged `phase-10`. Nothing pushed, no remote touched,
  `v0.1.0` not tagged.
- `.env` back to `MOCK_LLM=1` and the committed default model, never
  staged. It differs from `.env.example` only in the redacted secret and
  one stale comment line.
- The stack is up in fixture mode. `make down` clears it, including the 29
  incident rows the live run generated and the 2 the stopped collection
  added.
- Outstanding for the release decision: defect 13, still untested against a
  live model, and behind it the three-sample collection and the README
  table update. Both need a large-model budget that is genuinely 24 hours
  clear of the last suite.

## Phase 11

Run on 2026-08-08, branch `phase-11` off `phase-10`, same machine and
stack. A measurement pass only: no code, prompt, or assertion changed, and
`git status` was clean at the start and stays clean apart from this file
and the README. There is no `plan/phases/phase-11.md`; the brief came in
directly and is restated at the top of each step below.

The live suite reached 16 of 18 with zero rate limits, and it answered the
question three passes had been unable to reach. `test_latency_heals`
passes. It also showed why that pass proves less than it looks: across 24
live diagnoses the model called `query_traces` zero times. Phase 10 built
that tool and the prompt rule that depends on it, and the live model has
still never used either. `test_cache_outage_heals` fails, and the way it
fails is the same behaviour with the sign flipped.

### Step 1: the budget gate, and a key change

The brief required a real token reservation rather than a 200 on a small
request. Groq charges TPD against reserved `max_tokens`, so a 30-token
request can succeed with almost nothing left. The committed key was
exhausted:

```
$ probe: model=llama-3.3-70b-versatile requested_max_tokens=20000
status 429
  Rate limit reached for model `llama-3.3-70b-versatile` in organization
  `org_01kzdeh5t2e5pvgbrxct4fkpgz` ... on tokens per day (TPD):
  Limit 100000, Used 94035, Requested 20041.
  Please try again in 3h22m41.663999999s.
```

5,965 tokens against the roughly 95,000 the full brief needed. A second key
was supplied for the run. It belongs to a different organization
(`org_01kzft69ksexkr6dz5dww8ytr6`) and so carries its own untouched pool:

```
$ probe: requested_max_tokens=20000
status 413   ... on tokens per minute (TPM): Limit 12000, Requested 20041

$ probe: requested_max_tokens=11000
status 200
  x-ratelimit-limit-tokens: 12000
  x-ratelimit-remaining-tokens: 959
  content: ok
```

Both lines are needed to call the gate passed. Groq checks TPD before TPM,
so a 20,041 request that fails only on the per-minute cap has already
cleared the daily one. The 11,000 request then took the reservation for
real: remaining-tokens fell from 12,000 to 959, which is 11,041 held, not a
30-token courtesy 200.

### The daily limit is a leaky bucket, not a rolling window

Phase 10 read the TPD as a 24 hour window keyed to when tokens were spent
and predicted "the bulk of the window frees around 19:47Z on 2026-08-08".
That is wrong, and the retry-after strings say so. Against a bucket
refilling continuously at limit/24h:

```
old key 20041  deficit= 14076 predicted= 3.38h  told= 3.38h  err= 0.0%
old key 30041  deficit= 24129 predicted= 5.79h  told= 5.79h  err= 0.0%
new key 20041  deficit= 16446 predicted= 3.95h  told= 3.95h  err= 0.0%
```

Three points, exact. The refill is 4,166.7 tokens per hour and never
arrives in a lump. Nothing "frees up" at a particular clock time, and
waiting for a specific past run to age out is not a thing that happens.
Budget for a run by dividing what it costs by 4,167 to get the hours of
accrual it needs. This supersedes defect 15 as phase 10 stated it.

### Step 2: make e2e-live, 16 of 18

`.env` set to `MOCK_LLM=0` with the supplied key, containers recreated at
04:39:37Z, all five chaos toggles confirmed `fault_present: false`, and
three minutes of warm-up first, since phase 10 established that a cold
stack is what fails the detection-timeout tests.

```
### live e2e start 2026-08-08T04:46:33Z LLM_LARGE=llama-3.3-70b-versatile
MOCK_LLM=0 .venv/bin/python -m pytest e2e -q
..........F......F                                                       [100%]
FAILED e2e/test_detection_episodes.py::test_a_held_fault_opens_one_incident_per_pair
FAILED e2e/test_scenarios.py::test_cache_outage_heals - TimeoutError: inciden...
2 failed, 16 passed in 1149.68s (0:19:09)
exit=2
### live e2e end 2026-08-08T05:06:00Z
```

```
$ docker logs aegis-core-worker-1 | grep -c "Rate limit"
0
```

Zero 429s, against phase 10's 12. Every failure below is about behaviour.

```
model                    | runs | tokens_in | tokens_out | total | cost
llama-3.1-8b-instant     |   44 |     29566 |       2259 | 31825 | $0.00176
llama-3.3-70b-versatile  |   49 |     82678 |       3479 | 86157 | $0.05150

incidents: 26, 20 resolved, 6 escalated
```

### test_latency_heals passes, and the reason it proves less than it looks

The brief asked for whatever this test did, recorded. It passed, in both
latency incidents the run produced, and the assertion it clears is the
strict one: `_assert_healed` requires `fault_present is False` after the
actions ran, so restarting the cache and leaving the toxic in place cannot
pass it.

```
04:53:33.578 incident.detected      latency_p95 target-orders value=4849.99 threshold=1000.0
04:53:34.954 agent.run.started      triage   llama-3.1-8b-instant
04:53:35.237 incident.classified    sev2
04:53:35.241 agent.run.started      diagnose llama-3.3-70b-versatile
04:53:35.705 agent.step             submit_diagnosis
04:53:35.712 agent.run.completed    diagnose tokens_in=1646 tokens_out=71 duration_ms=464
04:53:36.189 action.proposed        remove_toxic tier=green {"toxic_name": "orders_shopdb_latency"}
04:53:36.266 action.policy_checked  allow  opa_rule_id=allow_green_tier
04:53:36.364 action.executed        {"toxic": "orders_shopdb_latency", "removed": true}
04:53:36.812 verify.passed
04:53:36.826 incident.resolved      autonomy=auto mttr_seconds=3
```

Defect 13's symptom did not reproduce. The model named the database toxic
and removed it, twice, and nothing carried
`[injected fault still present at verify]`.

The line that matters is `agent.step submit_diagnosis` arriving 464ms after
diagnose started, with no tool call before it. Phase 10's `query_traces`
returns the per-dependency timings that separate a slow database from a
slow cache, and the phase 10 prompt says a claim has to rest on a tool
output the model read. The model read nothing. Counted over every diagnose
run in the suite:

```
submit_diagnosis: 24
query_metrics:     5
query_logs:        5
query_traces:      0
```

Zero calls to `query_traces` in 24 diagnoses. Phase 10 could not test its
evidence layer because the budget died; phase 11 had the budget and the
layer went untouched anyway. That is a different and more useful negative
result: the tool is not being reached, so its quality was never the
binding constraint.

### test_cache_outage_heals fails, and it is the same behaviour

`cache_outage` pauses `shop-redis` (`actions/execute.py`), which raises p95
on target-orders and fires the same `latency_p95` rule as the `latency`
scenario. The fixture path heals it with `restart_dependency` on
`shop-redis`. Live:

```
05:01:57 incident.detected     latency_p95 target-orders 7140.6ms
05:02:35 action.executed       restart_service {"service": "target-orders"}
05:03:36 verify.failed
05:03:39 action.executed       restart_service {"service": "target-orders"}
05:03:45 action.rolled_back
05:03:46 action.executed       remove_toxic {"toxic_name": "orders_shopdb_latency"} -> removed: false
05:04:48 verify.failed
05:04:49 action.executed       remove_toxic {"toxic_name": "orders_shopdb_latency"} -> removed: false
05:05:50 verify.failed
05:05:53 action.executed       remove_toxic {"toxic_name": "orders_shopdb_latency"} -> removed: false
05:06:09 verify.passed
05:06:09 incident.resolved     autonomy=auto mttr_seconds=251
```

Three attempts to remove a toxic that was never installed, each answered
`removed: false`. Its four diagnose runs called `query_metrics` and
`query_logs` and never `query_traces` or `get_container_stats("shop-redis")`,
which is the paused-cache route the phase 10 prompt describes.

The `resolved` on the last line is an artifact and must not be read as a
heal. `wait_for_resolution` gives up at 240s, which lands at 05:05:57, and
the test's `finally` then calls `DELETE /api/chaos/cache_outage` and
unpauses `shop-redis`. Verification passed 12 seconds later against a stack
the test had already fixed. The agent never healed this incident, and 251s
is not an MTTR.

Put beside the latency result, one behaviour explains both. On a
`latency_p95` incident this model answers `remove_toxic` without looking.
The `latency` scenario is a toxic, so that lands. `cache_outage` is a
paused container, so it cannot.

### The other failure is upstream of diagnosis

```
E       TimeoutError: no incident for error_rate/target-payments within 90s
```

`test_checkpoint_resume` kills core-worker on purpose, and the restart is
visible:

```
2026-08-08 04:39:37,630 worker detection: 8 firing episodes rebuilt from the incidents table
2026-08-08 04:49:31,788 worker detection: 8 firing episodes rebuilt from the incidents table
```

The fault was injected at 04:50:15, 44 seconds after that rebuild. An
`error_rate` incident did open for target-gateway at 04:50:47 and none for
target-payments, which is what defect 3's one-incident-per-(rule, service)
episode rule does when the rebuild carries an episode forward that the
resolved 04:47:06 payments incident had opened. Nothing this phase or
phase 10 touched is involved, and the same message failed a fixture run in
phase 10. Recorded as an observation about test ordering, not as a new
defect, since the mechanism is a deliberate feature and the reproduction is
a worker kill from another test file.

### Step 3: the collection, not run, and the arithmetic for why

The brief asked for three samples each of `error_spike` and `cache_outage`.
It was not run. The suite left 3,595 tokens:

```
$ probe after the suite: requested_max_tokens=20000
status 429
  ... Limit 100000, Used 96405, Requested 20041.
```

Sized from this run's own per-incident figures rather than phase 8's
estimate:

| scenario                     | large tokens/sample | three samples |
| ---------------------------- | ------------------- | ------------- |
| error_spike (heals)          | 3,120               | ~9,400        |
| cache_outage (does not heal) | 21,321              | ~64,000       |

A failing `cache_outage` costs seven times a healthy incident because each
failed verification buys another diagnose, plan and act cycle until the
240s limit. At 4,167 tokens per hour the pair needs about 17 hours of
accrual, and roughly 64,000 of it would document six more failures of a
scenario this run already characterised once. Skipped as a deliberate
decision, not a budget accident. No number in the README's measured table
moved and the `cache_outage (n=1)` caveat stays.

### The 20% band: all five rows fail

plan/07 item 2 requires live MTTR within 20% of the README's claims.
Checked against this run's incidents, mapped by test execution order:

```
scenario        README   phase 11         band 20%  verdict
latency            92s         3s          74-110s  FAIL (3% of claim, n=2)
crash              61s         8s           49-73s  FAIL (13% of claim, n=1)
error_spike       132s        85s         106-158s  FAIL (64% of claim, n=1)
memory_leak        21s         7s           17-25s  FAIL (33% of claim, n=1)
cache_outage      136s    no heal         109-163s  FAIL (fault never cleared by agent)
```

Four of the five are far faster than claimed, which is not good news. The
README's numbers come from phase 6 on `openai/gpt-oss-120b`, `gpt-oss-20b`
and `qwen3.6-27b`; these come from `llama-3.3-70b-versatile` skipping its
evidence tools. An MTTR that collapses from 92s to 3s is the diagnosis step
ceasing to do work, not the system getting faster. The table was left
alone per the decision above, and the README's "What this is not" now says
plainly that none of the five reproduces on the current model.

### README

The measured table is untouched. "What this is not" was rewritten against
this run: the zero `query_traces` calls in 24 diagnoses, `latency` healing
correctly in 3s without reading any trace timing, `cache_outage` not
healing at all and its recorded time coming from test cleanup, the rollback
that fired when verification failed, and the band result. The previous
paragraph's claim, that the model reads database latency as a cache fault
"roughly as often as not", is now contradicted by evidence and was removed.

### Defect table

| #   | Severity | What                                                                                                                                               | Status                                     |
| --- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| 13  | medium   | Live diagnose reads database latency as a cache fault, so `latency` heals with `restart_dependency` and the toxic survives a passing verify        | symptom not reproduced, mechanism unproven |
| 14  | medium   | `query_traces` searched recent traces, not slow ones, and reported no per-span timings                                                             | fixed (phase 10), still never called live  |
| 15  | low      | The token cap was read as a per-calendar-day and then as a rolling 24h window; it is a bucket refilling at 4,167 tokens/hour                       | corrected (phase 11), no code change       |
| 16  | high     | Live diagnose answers every `latency_p95` incident with `remove_toxic` without calling a tool, so `cache_outage` (paused `shop-redis`) never heals | open, reproduced once                      |

Defect 13 does not close. Two samples healed correctly and neither read any
evidence, so what phase 10 built is still unproven and the pass is not
attributable to it. Defect 14 stays fixed and unexercised, for the second
pass running, now because the model does not call the tool rather than
because the budget ran out. Defect 16 is new and is filed above 13 in
severity: an incident that closes without healing is worse than one that
heals for the wrong reason, and this one is only labelled correctly by
accident of the test's own cleanup.

### State this section leaves behind

- Branch `phase-11`, tagged `phase-11`. Nothing pushed, no remote touched,
  `v0.1.0` not tagged.
- `.env` restored byte-identical to its pre-run backup: `MOCK_LLM=1` and
  the committed key. The key used for the run belongs to a different Groq
  organization, was supplied for this run only, and was never staged.
- All five chaos toggles verified `fault_present: false` after the run. The
  stack is up in fixture mode with 26 incident rows from this run; `make
down` clears them.
- Outstanding for the release decision: defect 16, which is a live
  scenario that does not heal, and behind it the question defect 13 and 14
  now share, which is why diagnose reaches for no tools at all on this
  model.

## Phase 12

Run on 2026-08-08, branch `phase-12` off `phase-11`, same machine and
stack. The deletion this phase exists for is done and committed. The live
run that was supposed to measure its effect was not taken, and the fixture
gate did not reach 18/18 either. The daily token budget was gone before
the live suite could reach a diagnose call, and a large part of it went on
this session's own oversized probe reservations and on two e2e suites that
ran against the stack at the same time by accident. The fixture gate was
attempted four times on a machine whose Docker daemon wedged twice and
whose swap was within 700MB of full, and its best pass is 16 of 18 with
both misses timing out in setup. Both are recorded below in full, because
a phase report that describes a measurement it did not take is worse than
one that says it missed.

So the honest state after phase 12: the answer key is out of the prompt,
and nobody yet knows what the model does without it.

### Housekeeping: the tags already existed

The brief asked for `phase-10` and `phase-11` to be created on `d35d4f2`
and `4ddceae`. Both were already there. What makes them look absent is a
branch of the same name sitting beside each tag, so a bare rev-parse warns
before it answers:

```
$ git rev-parse phase-10 phase-11
warning: refname 'phase-10' is ambiguous.
warning: refname 'phase-11' is ambiguous.
d35d4f24d20b9800d6084ef8a540110d2d5ab0f4
4ddceaeafabc03148a70856ac0b3560a2849e164

$ git for-each-ref refs/tags --format='%(refname:short) %(objectname:short) %(subject)'
tags/phase-10 d35d4f2 docs: phase 10 results, an evidence fix the live model never got to read
tags/phase-11 4ddceae docs: phase 11 live results, a latency pass that read no evidence
```

Both point at the right commits. Nothing was created and nothing moved.

### Step 1: what came out of diagnose.md

The paragraph the reviewer found, gone in full:

```
Known fault patterns in this system: a proxy adding latency between orders
and its database; a service process stopped or crash-looping; a bad
feature flag causing elevated error rates; unbounded memory growth ending
in an OOM kill; a paused cache dependency. Match the evidence to the
pattern it actually supports; do not guess ahead of the evidence.
```

Reading the rest of the prompt against the brief's three tests (names an
injected fault, names a container by its role in a scenario, or offers an
action as the answer to a symptom) turned up two more sentences.

The tool paragraph justified `get_container_stats("shop-redis")` by naming
the scenario it solves: shop-redis container state "is the evidence for a
paused-cache incident". That is the fifth list item restated as a tool
note. It now says only that the tool accepts that argument and that no
target service's stats describe it.

The workflow paragraph opened by enumerating four of the five faults as
the things metrics and logs name for you: "A stopped process, a crash
loop, an OOM kill, or an error rate with a recent config change behind
it". That is the list again, in the section that was supposed to teach
method. It now says that when something has broken outright those two
tools usually name it.

The same paragraph also routed symptoms to a named suspect ("If the slow
call is into the database path... the cache is not it. If the slow call is
to the cache... call get_container_stats("shop-redis")"). The method
underneath survives without the names: the dependency whose call holds the
time is where the cause is, a dependency that answered quickly is not, and
no slow traces at all can mean a dependency that never answers, which is
what get_container_stats on that dependency is for.

What stays is what the brief said stays. Which tool answers which
question. That slowness needs traces before a cause is named. The three
evidence rules, the 8-call ceiling, the untrusted-output warning, and the
topology sentence at the top, which describes the system rather than the
faults injected into it.

```
$ git show --stat 09f1d48
 apps/core/aegis/agents/prompts/diagnose.md | 36 ++++++++++---------------
 plan/phases/phase-12.md                    | 43 ++++++++++++++++++++++++++++++
 2 files changed, 57 insertions(+), 22 deletions(-)

$ docker exec aegis-core-worker-1 grep -c "Known fault patterns" /app/aegis/agents/prompts/diagnose.md
0
```

The second command matters because the prompt is baked into the image, not
mounted from the repo. Every run below is against a rebuilt worker.

### The other three prompts, and where the answer key still lives

`triage.md`: nothing. It names the topology and the three severity bands,
no injected fault, no container by scenario role, no catalog action. One
line pushes the other way: "summary states what is observed, not a guess
at the cause; diagnosis happens next."

`verify.md`: nothing. It names no scenario and no action, and it pins
`passed` to the probe tool's `all_healthy` rather than to the model's
judgment.

`plan_remediation.md`: the same answer key, from the same commit
(`e7f8b2e`, phase 2), in a stronger form than diagnose.md ever had it.
Three of the five scenarios appear with their fix and its exact
parameter already filled in:

```
- The latency fault is a single Toxiproxy toxic named
  `orders_shopdb_latency` on the `shopdb` proxy between target-orders and
  its database. If the hypothesis is added network/database latency,
  `remove_toxic` with `params.toxic_name = "orders_shopdb_latency"` clears
  it directly.
- If a target service's process is stopped or crash-looping, `restart_service`
  with `params.service` set to that service's name is the direct fix.
- An elevated error rate on target-payments is a bad feature flag on that
  service. `rollback_config` with `params.service = "target-payments"`
  restores its last good config and restarts it.
```

The catalog table above it does the same job a column at a time
("restart_service | a target service's process is stopped or
crash-looping", "rollback_config | a bad config or feature flag on a
target service, which is what an elevated error rate on that service
almost always is").

It was left in place, deliberately, for two reasons. The brief's
experiment is one deletion, and cutting two prompts in the same run would
make any change in behaviour unattributable. More importantly the two are
not equivalent: `plan_remediation` runs after `diagnose` and its prompt
never reaches the diagnose node, so nothing in it can teach the model what
is wrong. It can only route a hypothesis that already exists to a catalog
key. The diagnose list answered the question; this one fills in a
parameter once the question is answered.

That is a reason to keep the phase clean, not a defence of the block. It
should come out, and it needs its own phase, because removing it will move
remediation quality and there has to be a run that can attribute the
change. One consequence to keep in mind when the live numbers finally
arrive: a vague hypothesis out of diagnose can still land the right action,
because these three lines are sitting downstream ready to catch it. A
passing scenario after this phase is not by itself proof that diagnosis
improved.

Verified the block is not mirrored anywhere the model can reach it:

```
$ grep -rn "crash-looping\|feature flag\|OOM kill\|paused cache\|fault pattern" apps/core/aegis/
apps/core/aegis/chaos.py:120:  # an OOM kill leaves it stopped so service_down has time to
apps/core/aegis/chaos.py:213:  # memory_leak: the flag lives in the process, so an OOM kill clears it by
apps/core/aegis/agents/prompts/plan_remediation.md:12,17,28,35   (above)
apps/core/aegis/actions/docker_ops.py:53:  # fires for both crash (docker stop) and memory_leak (OOM kill) on the
```

The three code hits are comments in the chaos injector and the executor,
neither of which the diagnose model sees. The five diagnosis tool
descriptions in `tools.py` name no fault. The `scenario` field on
AgentState is passed to `run_agent_node` for fixture selection only; the
diagnose node's `user_content` is the incident record and the detection
snapshot, and nothing else (`nodes/diagnose.py:22-36`).

### Step 3: the live run did not happen

Taking this out of order, because it is what the phase was for.

The gate the brief required passed. A real 11,000-token reservation, not a
courtesy 200 on a small request:

```
$ probe: model=llama-3.3-70b-versatile requested_max_tokens=11000
status 200
  x-ratelimit-limit-tokens: 12000
  x-ratelimit-remaining-tokens: 960
  content: ok
```

Remaining fell from 12,000 to 960, so 11,040 was actually held. Two hours
later, after the suite had been started and killed twice, the same probe:

```
$ probe after the aborted runs: requested_max_tokens=11000
status 429
  Rate limit reached for model `llama-3.3-70b-versatile` in organization
  `org_01kzdeh5t2e5pvgbrxct4fkpgz` service tier `on_demand` on tokens per
  day (TPD): Limit 100000, Used 98356, Requested 11040.
  Please try again in 2h15m18.144s.
```

Where the budget went, in order:

1. The gate probe at 06:39Z: 11,040 held, and it was charged.
2. A follow-up probe at 30,000 max_tokens, run to measure how much daily
   headroom was left. It returned 200 and charged the reservation. This
   was the single most expensive mistake of the session: it spent 30,041
   tokens to answer a question the gate had already answered well enough.
3. Two more 11,000 probes, one of them a re-run of the gate immediately
   before the suite.
4. Two partial e2e suites. The second was an accident: a warm-up wrapper
   from an earlier attempt fired late and started a second `pytest e2e`
   against the same stack 106 seconds after the first, so for about two
   minutes two suites drove the same worker and blew through tokens at
   double rate. Both were killed once that was noticed.

By the time a clean suite started at 08:45:08Z there was nothing left. Its
four diagnose runs all died on 429 before the model produced a single
turn:

```
$ select agent, status, count(*), sum(tokens_in) from aegis.agent_runs
  where started_at > '2026-08-08T08:36:30Z' group by 1,2;
diagnose|failed|4|0
triage|completed|4|2595

$ select payload->>'tool', count(*) from aegis.incident_events
  where type='agent.step' and payload->>'thought_summary' like 'diagnose called%'
    and created_at > '2026-08-08T08:36:30Z' group by 1;
(0 rows)
```

Zero rows. Not "the model called no tools", which is what phase 11 found
and what this phase set out to re-measure. Zero rows because the model was
never reached. The 429s are in the worker log with the reason attached:

```
$ docker logs aegis-core-worker-1 | grep -c "Rate limit"
16
$ ... | grep -o "on tokens per day (TPD): Limit [0-9]*, Used [0-9]*, Requested [0-9]*" | tail -1
on tokens per day (TPD): Limit 100000, Used 98733, Requested 1537
```

### Step 4: the tool call counts, which is the thing that is missing

The brief asked for the phase 11 breakdown per diagnose run, and called it
"the actual measurement this phase exists to take". There is no such table
in this report. The measurement was not taken and no number is offered in
its place. Phase 11's figures stand as the last real ones:

```
submit_diagnosis: 24
query_metrics:     5
query_logs:        5
query_traces:      0
```

Those were produced with the fault list in the prompt. Whether removing it
changes them is exactly the open question, and it is still open.

### What it will cost to actually take it

At the leaky-bucket rate phase 11 established, and phase 11's own measured
suite cost of 86,157 large-model tokens, the run needs `86157 / 4167 =
20.7` hours of accrual from an untouched key. From `Used 98356` at
08:46:22Z that is `(98356 - 13843) / 4167 = 20.3` hours, so a clean window
opens around 05:05Z on 2026-08-09. Anything that spends large-model tokens
before then pushes it out one hour per 4,167 spent, which includes probe
reservations: the lesson from item 2 above is that the gate is a single
11,000 request and nothing more.

### The bucket model gets a fourth exact data point

Phase 11 established that the daily cap is a bucket refilling at 4,167
tokens per hour rather than a window that frees at a clock time, on three
points. The 429 above is a fourth:

```
deficit = 98356 + 11040 - 100000 = 9396
predicted = 9396 / 4166.7 = 2.255h = 2h15m18s
told      = 2h15m18.144s
err       = 0.0%
```

### Step 2: fixtures

The gate is not green. It was run four times and never reached 18/18 in a
single pass, and no failure in any of them was an assertion about what an
agent decided.

The first run, before the machine degraded, on a warm stack:

```
$ MOCK_LLM=1 make e2e
1 failed, 17 passed in 1022.82s (0:17:02)
FAILED e2e/test_scenarios.py::test_cache_outage_heals - httpx.ReadTimeout: timed out
```

The last run, after restarting the worker to clear the connection defect
described below:

```
### fixture e2e retry start 2026-08-08T09:36:06Z
MOCK_LLM=1 .venv/bin/python -m pytest e2e -q
.EE..............
ERROR e2e/test_approval_reload.py::test_a_parked_approval_survives_a_page_reload
ERROR e2e/test_approvals.py::test_signed_approval_wakes_the_parked_run
16 passed, 2 errors in 2152.97s (0:35:52)
### fixture e2e retry end 2026-08-08T10:12:06Z
```

Zero failures in that one. Both errors are the same thing, and both happen
in setup, before the test body runs:

```
E  subprocess.TimeoutExpired: Command '['docker', 'compose', '-f',
   'deploy/docker-compose.yml', 'exec', '-T', 'core-api', 'python', '-']'
   timed out after 180 seconds
```

A `docker compose exec` that seeds an approver key, timing out after three
minutes. The same suite took 17 minutes in the first run and 36 in the
last, on the same machine, with the same fixtures. Host swap was at
10,542MB of 11,264MB used while the last one ran.

Between the two runs every one of the 18 tests passes: `cache_outage` in
the second, the two approval tests in the first. No run has all 18 at
once. The run in between was worse (11 passed, 4 failed, 3 errors, 38
minutes) and is accounted for by the checkpointer defect below, which
crashed 9 agent runs and escalated the incidents they belonged to,
including the one behind `AssertionError: assert 'escalated' == 'resolved'`
on `test_error_spike_heals`, an incident whose `severity` is `None`
because triage never finished.

The prompt change cannot be the cause of any of this, and the reason is
structural rather than circumstantial: under `MOCK_LLM=1` no prompt is
sent anywhere. `_call_mock` in `apps/core/aegis/llm.py` takes
`(incident_id, scenario, node)`, reads
`apps/core/fixtures/<scenario>/<node>_<n>.json`, and returns the recorded
tool calls. It never receives the system prompt and never looks at one.
Editing `diagnose.md` cannot change a fixture run's behaviour by any path.

That is an argument, not a green gate, and it does not discharge the
brief's requirement. 18/18 on one pass still has to be produced on a
machine that can hold the stack still for 20 minutes.

### Three fixtures were recorded off the answer key

The brief asked for fixtures to be re-recorded if any of them was recorded
against the deleted block and now misleads. Three were, and they quote it
close to verbatim:

```
apps/core/fixtures/error_spike_target-gateway/diagnose_1.json
  submit_diagnosis  evidence_refs=[]
  "The root cause of the incident is a bad feature flag causing elevated
   error rates on target-gateway."

apps/core/fixtures/latency_target-gateway/diagnose_1.json
  submit_diagnosis  evidence_refs=['query_metrics(target-gateway)', 'query_logs(target-gateway)']
  "The root cause of the incident is a service process stopped or
   crash-looping in the target-gateway service, resulting in high latency
   and error rates."

apps/core/fixtures/latency_target-orders/diagnose_1.json
  submit_diagnosis  evidence_refs=['query_metrics(target-orders)']
  "The root cause of the incident is a proxy adding latency between orders
   and its database, resulting in high p95 latency on target-orders."
```

"a bad feature flag causing elevated error rates", "a service process
stopped or crash-looping", "a proxy adding latency between orders and its
database" are the third, second and first items of the deleted list, in
the list's own words. All three are turn 1, so all three named a root
cause before making any tool call, and two of them cite `evidence_refs`
for calls that had not happened. The gateway one is also simply wrong: it
answers a latency scenario with a crash-loop.

They were not re-recorded. `make record-fixtures` runs the scenario
against the real model, and by the time this was confirmed the budget was
the state shown above. Re-recording all three is cheap next to the suite
(on phase 11's per-incident figures, roughly 3,000 large tokens each), so
it belongs in the same window as the live run, before the suite rather
than after, and the fixtures should be re-recorded first so the suite runs
against turns the current prompt could actually produce.

Left as they are, they are the clearest surviving artifact of what the
deleted paragraph did: three recordings of a model reading an answer out
of its own instructions.

### An unrelated defect found while running the suite

Twice during the session the worker's LangGraph Postgres checkpointer lost
its connection and never got it back. Every incident opened afterwards
failed the same way and escalated:

```
2026-08-08 07:04:06,501 worker agent run for incident inc_01KZG2Z8FTGAH2SP9FM8QNCK5V crashed
Traceback (most recent call last):
  File "/app/aegis/agents/graph.py", line 130, in run_incident
    await graph.ainvoke(state, config=_graph_config(incident_id))
  ...
  File "/usr/local/lib/python3.12/site-packages/langgraph/checkpoint/postgres/aio.py", line 386, in _cursor
    async with conn.cursor(binary=True, row_factory=dict_row) as cur:
  File "/usr/local/lib/python3.12/site-packages/psycopg/_connection_base.py", line 528, in _check_connection_ok
    raise e.OperationalError("the connection is closed")
psycopg.OperationalError: the connection is closed
```

`AsyncPostgresSaver` holds one connection and has no reconnect path, so a
single dropped connection takes the worker out permanently while it keeps
reporting healthy and keeps accepting incidents. A `docker compose restart
core-worker` fixes it. It is filed as defect 17 below. It is not related
to anything this phase changed, and it is the reason two of this session's
suite runs are not reported as results.

### The machine

Docker Desktop wedged twice, hard enough that `docker ps` and `docker
version` stopped answering and the quit AppleScript was ignored (the same
PIDs survived it). Recovery both times was a `pkill` of `Docker Desktop`
and `com.docker.backend` followed by a relaunch. `docker builder prune -f`
reclaimed 5.911GB, and host swap was at 12,166MB of 13,312MB used when the
first wedge happened. Four suite runs were lost to this before one
completed. Noted here so the next phase budgets for it rather than
rediscovering it.

### Defect table

| #   | Severity | What                                                                                                                                                                    | Status                                       |
| --- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| 13  | medium   | Live diagnose reads database latency as a cache fault, so `latency` heals with `restart_dependency` and the toxic survives a passing verify                             | open, cause removed, re-measurement pending  |
| 14  | medium   | `query_traces` searched recent traces, not slow ones, and reported no per-span timings                                                                                  | fixed (phase 10), still never exercised live |
| 15  | low      | The token cap was read as a per-calendar-day and then as a rolling 24h window; it is a bucket refilling at 4,167 tokens/hour                                            | corrected (phase 11), confirmed again        |
| 16  | high     | Live diagnose answers every `latency_p95` incident with `remove_toxic` without calling a tool, so `cache_outage` (paused `shop-redis`) never heals                      | open, likely cause removed, unverified       |
| 17  | high     | The worker's LangGraph Postgres checkpointer never reconnects after a dropped connection; the worker stays up, reports healthy, and escalates every incident it accepts | open, found phase 12, reproduced twice       |

None of 13, 14 or 16 moves on evidence this phase, because this phase
produced none. What changed is the leading explanation for all three. The
phase 11 reading was that the model receives a symptom, matches it against
the list in its prompt, and answers without looking; that list is now gone,
which makes the next live run a real test of the reading rather than a
repeat of it. Writing them down as fixed on that basis would be exactly the
mistake phase 10 made when it recorded an evidence fix the live model
never got to read.

Defect 16 keeps its high severity and its wording. Defect 13 stays open
for the second phase running with its symptom unreproduced and its
mechanism unproven.

### README

The measured table is untouched, and no number in it moved. "What this is
not" keeps the phase 11 paragraphs, which are still the last real
measurement, and gains a note that the prompt those numbers were produced
under no longer exists: the fault list came out in phase 12 and the
re-measurement has not been run. Nothing was rewritten to claim an
improvement that has not been observed.

### Lint and unit tests

```
$ make lint
ruff + mypy clean, eslint clean, prettier: All matched files use Prettier code style!

$ make test
88 passed, 2 warnings in 3.87s          (pytest apps/core)
Test Files  8 passed (8), Tests 46 passed (46)   (vitest, console)
PASS: 9/9                                (opa test packages/policies)
```

The two mechanical checks from `scripts/gate.sh` that apply to a docs and
prompt change, run directly since the script also wants a
`PHASE_12_REPORT.md` that phases 10 and 11 did not produce either:

```
$ git grep -In $'\xe2\x80\x94' -- . ':!plan' ':!PLAN.md' ':!scripts/gate.sh'
(no matches)
$ git grep -n "shell=True" -- apps/
(no matches)
```

### State this section leaves behind

- Branch `phase-12`, tagged `phase-12`. Nothing pushed, no remote touched,
  `v0.1.0` not tagged.
- `.env` restored byte-identical to its pre-run state, verified by
  checksum: `4c9e677cd3d55f00a4396eff39230081` before and after,
  `MOCK_LLM=1`.
- All five chaos toggles verified `fault_present: false` after the run.
- The large-model key is at `Used 98356` of 100,000 and needs roughly 20
  hours of accrual before the live suite can be attempted, so about 05:05Z
  on 2026-08-09.
- Outstanding, in order: the live run this phase did not take, the three
  fixtures to re-record in the same window, defect 17, and the
  `plan_remediation.md` block, which is the same answer key one node
  downstream.

## Phase 13

Run on 2026-08-08, branch `phase-13` off `phase-12`, same machine and
stack. The second answer key is out, defect 17 is fixed and tested, the
three poisoned fixtures are re-recorded, the fixture gate ran in one pass,
and the live suite ran and died 2 minutes 25 seconds in on the daily token
cap.

The measurement the phase exists to take came out, at n=5 rather than the
24 phase 11 had, and it is not the result the deletion was hoping for.
`test_latency_heals` now fails, on fixtures and live, because a model with
no answer key proposes `restart_service` for a Toxiproxy toxic. The brief
said in advance that a suite scoring worse while actually reading evidence
is the better outcome. This is half of that. The other half is a
verification bug that was hiding underneath the answer key, filed below as
defect 18.

### Step 1: what came out of plan_remediation.md

The brief named three bullets. There were four, and the fourth fails the
same three tests phase 12 used on diagnose.md (names an injected fault,
names a container by its role in a scenario, offers an action as the
answer to a symptom), so it came out with them:

```
- The latency fault is a single Toxiproxy toxic named
  `orders_shopdb_latency` on the `shopdb` proxy between target-orders and
  its database. If the hypothesis is added network/database latency,
  `remove_toxic` with `params.toxic_name = "orders_shopdb_latency"` clears
  it directly.
- If a target service's process is stopped or crash-looping, `restart_service`
  with `params.service` set to that service's name is the direct fix.
- If the shared Redis cache dependency itself is paused or unresponsive
  (not a target service), `restart_dependency` with `params.service =
  "shop-redis"` restarts it directly; `restart_service` only takes a
  target service name and cannot fix this. `shop-redis` is the only
  cache container you may name.
- An elevated error rate on target-payments is a bad feature flag on that
  service. `rollback_config` with `params.service = "target-payments"`
  restores its last good config and restarts it.
```

The third is the `cache_outage` scenario written out as an instruction:
paused cache, named container, named action, in that order. Phase 12
quoted the other three, which is why the brief says three.

The table's `use it when` column went with them, because it was the same
mapping a row at a time ("a target service's process is stopped or
crash-looping", "a bad config or feature flag on a target service, which
is what an elevated error rate on that service almost always is"). What
the table carries now is `catalog_key`, `tier`, and the `effect` string
out of `apps/core/aegis/actions/catalog.yaml`: what the executor will do
if the key is chosen, rather than a reason to choose it.

One judgment call, flagged because it sits on the line between the
contract and the answer. The closed param sets stayed:

```
- `service` on restart_service, scale_service and rollback_config is one
  of target-gateway, target-orders, target-payments.
- `service` on restart_dependency is one of shop-redis, toxiproxy.
- clear_cache, flush_queue and restart_database take no params.
```

Those are enumerations the executor validates against (`catalog.yaml`,
`service: {enum: [shop-redis, toxiproxy]}`), and `get_catalog` does not
expose them: it returns param names only (`"params": list(a.params)`,
tools.py:292). A model that cannot name a legal value cannot call the
action at all, which would test nothing. Every sentence saying which
symptom a value answers is gone.

`orders_shopdb_latency` is not in catalog.yaml and did not survive on that
rule. Nothing in any prompt, tool description, tool output or state object
names it now, and no tool lists toxics. That consequence is the story of
the rest of this phase.

```
$ docker exec aegis-core-worker-1 grep -c "orders_shopdb_latency" \
    /app/aegis/agents/prompts/plan_remediation.md
0
$ docker exec aegis-core-worker-1 grep -c "use it when" \
    /app/aegis/agents/prompts/plan_remediation.md
0
```

The prompt is baked into the image rather than mounted, so every run below
is against a rebuilt worker.

### Step 2: defect 17

`AsyncPostgresSaver.from_conn_string` hands the saver one connection and
no way to replace it. The saver now runs over a pool:

```python
return AsyncConnectionPool(
    conninfo=checkpoint_conn_string(),
    connection_class=AsyncConnection[DictRow],
    min_size=CHECKPOINT_POOL_MIN_SIZE,
    max_size=CHECKPOINT_POOL_MAX_SIZE,
    open=False,
    check=AsyncConnectionPool.check_connection,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
        "application_name": CHECKPOINT_APP_NAME,
    },
)
```

`check` is the part that does the work. Without it a backend killed while
idle in the pool is handed straight back out on the next checkout. The
pool covers every run that asks for a connection after the drop; the run
that was holding one when it went still sees the `OperationalError` out of
its own checkpoint write, so `graph._invoke` retries that one, once,
resuming from the last persisted checkpoint rather than restarting the
incident. Only `psycopg.OperationalError` is retried: a model or policy
failure is not a connection problem, and retrying it would execute the
incident's remediation twice.

The health half needed a decision. core-worker had no healthcheck at all,
which is the literal reason phase 12 could write "stays up, reports
healthy": docker calls a container with no healthcheck running, and
nothing ever disagreed. It also exposes no port (plan/01-architecture.md,
Runtime topology, ports `none`), so an endpoint would have contradicted
the plan. `run_health_loop` probes the checkpointer every 10 seconds with
a real `aget_tuple` through the pool and touches
`/tmp/aegis-worker-health` only when that read comes back; the container
healthcheck fails the worker when the marker is older than 45 seconds.

```
$ docker compose ps --format '{{.Name}} {{.Health}}' core-worker
aegis-core-worker-1 healthy

$ psql -tAc "SELECT application_name, count(*) FROM pg_stat_activity
             WHERE datname='aegis' GROUP BY 1"
|5
aegis-checkpointer|2
psql|1
```

Five asyncpg backends carrying no application_name, two checkpointer
backends carrying one. The e2e test kills the second group and leaves the
first alone, which is what makes it a test of the connection rather than
of the process:

```
$ MOCK_LLM=1 .venv/bin/python -m pytest e2e/test_checkpointer_reconnect.py -q
.                                                                        [100%]
1 passed in 61.45s (0:01:01)
```

It injects `crash`, waits for `agent.run.started`, runs
`pg_terminate_backend` on every `aegis-checkpointer` backend, waits for
that incident to reach a terminal state, then opens a second incident and
asserts it resolves. Before the fix the second one always escalated. It is
skipped under `MOCK_LLM=0`: the mechanism is psycopg's pool and a retry in
`graph.py`, neither of which reads a model response, and two extra live
incidents are roughly 16,000 large-model tokens against a 100,000/day cap.
That skip is a deliberate trade and is the one thing in this phase's test
coverage that a paid tier should undo.

Five unit tests cover the retry and the health predicate without a
database, including the direction the e2e test cannot reach because the
pool recovers inside a second: a probe that raises writes nothing, the
marker ages out, and the worker reports unhealthy.

### Step 3: the fixture audit, and what re-recording showed

All seven `diagnose_1.json` files, read in full. Three name a cause on
turn 1 with no tool call, and they are exactly the three the brief named:

```
error_spike_target-gateway   submit_diagnosis   "a bad feature flag causing elevated error rates"
latency_target-gateway       submit_diagnosis   "a service process stopped or crash-looping"
latency_target-orders        submit_diagnosis   "a proxy adding latency between orders and its database"
```

The other four open with a tool call and were left alone:
`cache_outage_target-orders` and `crash_target-payments` and
`error_spike_target-payments` with `query_metrics`,
`memory_leak_target-payments` with `get_container_stats`.

One recording run regenerated all three, because a latency injection
cascades into a target-gateway `error_rate` incident and that is where the
third one comes from:

```
$ make record-fixtures SCENARIO=latency
injecting latency
resolved: inc_01KZGWKYE2J4W2NEEC6K6DVA9Q (error_rate/['target-gateway']) mttr=44s
resolved: inc_01KZGWKATXW6JKB4QF8X60FB91 (latency_p95/['target-gateway']) mttr=64s
resolved: inc_01KZGWK5XHZ2ZV93R8F0G7BQ7X (latency_p95/['target-orders']) mttr=14s
```

Cost: 6 large-model runs, 10,042 tokens in and 431 out; 6 small-model
runs, 4,079 in and 304 out.

What changed in the recordings is worth reading closely, because two
different things happened. target-orders got better:

```
-  submit_diagnosis  confidence 0.8  evidence_refs ["query_metrics(target-orders)"]
-  "The root cause of the incident is a proxy adding latency between
-   orders and its database"
+  query_metrics(target-orders)
+  query_logs(target-orders)
+  submit_diagnosis  confidence 0.8  evidence_refs ["query_metrics(...)", "query_logs(...)"]
```

It now reads two tools before it answers, and its `evidence_refs` name
calls that actually happened. The old one cited evidence for a call it had
never made.

Both gateway incidents got quieter rather than better:

```
-  confidence 0.8  evidence_refs ["query_metrics(...)", "query_logs(...)"]
-  "a service process stopped or crash-looping in the target-gateway service"
+  confidence 0.0  evidence_refs []
+  "the high p95 latency on target-gateway, which is currently 7304.1ms"
```

Still turn 1, still no tool call, but the fabricated `evidence_refs` are
gone, the invented fault is gone, and the model now rates its own
confidence at 0.0 while restating the symptom it was handed. By the
brief's criterion these two still "name a cause on turn 1 with no tool
call", so on the letter of it they would be re-recorded again. They were
not, and re-recording them would be circular: they are faithful
recordings of what the current prompt actually produces, which is the
thing the criterion was meant to get to.

One stale artifact cleared itself. `error_spike_target-gateway`'s plan
fixture used to propose `remove_bad_feature_flag`, a catalog_key that does
not exist, so the gate denied it and the incident escalated every time.
The re-recorded plan proposes `restart_service`, which is legal.

### Step 4: the fixture gate, in one pass

```
### fixture e2e start 2026-08-08T14:35:20Z
MOCK_LLM=1 .venv/bin/python -m pytest e2e -q
..............F....                                                      [100%]
E       AssertionError: latency: incident inc_01KZGXHBBP2P5G0DN7ERF4JN5E
        resolved but fault_present=True after actions ['restart_service']
E       assert True is False
FAILED e2e/test_scenarios.py::test_latency_heals
1 failed, 18 passed in 1287.68s (0:21:27)
### fixture e2e end 2026-08-08T14:56:51Z
```

19 tests now, not 18: `test_checkpointer_reconnect` is new. One pass, one
failure, no errors, no timeouts, 21 minutes. Both approval tests and
`test_cache_outage_heals` passed in the same run, which phase 12 never
managed across four attempts. Nothing was restarted mid-suite and the
worker stayed healthy throughout.

The failure is the deletion, arriving through the plan node rather than
the diagnose node. With no prompt naming the toxic, the model proposes
`restart_service` on target-orders. Restarting target-orders does nothing
to a toxic installed on the `shopdb` proxy, so the fault is still there
when the incident closes, and the assertion that catches it is the one
phase 9 wrote for exactly this: whichever catalog_key the model picks, the
fault has to be gone.

This is the honest state of the repo and it is being committed red. The
alternative was to keep fixtures that quote a prompt which no longer
exists, which would have kept the gate green on a recording of the model
reading its own instructions.

### Step 5: the live suite, and a gate that does not gate

The brief's gate passed:

```
$ probe: model=llama-3.3-70b-versatile requested_max_tokens=11000   (14:57:44Z)
status 200
  x-ratelimit-limit-tokens: 12000
  x-ratelimit-remaining-tokens: 963
  content: ok
```

Remaining fell from 12,000 to 963, so 11,037 was held, which is the test
phase 11 designed and phase 12 repeated. `.env` was switched to
`MOCK_LLM=0`, core-worker recreated, and `make e2e-live` started at
14:58:20Z with no other pytest process running. It reached test 11 of 19:

```
### live e2e start 2026-08-08T14:58:20Z
MOCK_LLM=0 .venv/bin/python -m pytest e2e -q
.........Fs
### live e2e end 2026-08-08T15:01:06Z
```

Nine passed, one failed (`test_checkpoint_resume`), one skipped (the new
checkpointer test, by design). It was killed at 15:01:06Z, 2 minutes 25
seconds after it started, because the worker log said this at 15:00:45:

```
Rate limit reached for model `llama-3.3-70b-versatile` in organization
`org_01kzdeh5t2e5pvgbrxct4fkpgz` service tier `on_demand` on tokens per
day (TPD): Limit 100000, Used 99600, Requested 1572.
Please try again in 16m52.608s.
```

Killing it was the call. Every later incident would have escalated on a
socket rather than a decision, which is phase 12's outcome repeated at
higher cost, and the trickle of refill would have been spent on garbage.

The gate is the thing to take away from this. It returned 200 at 14:57:44
and the suite was out of tokens at 15:00:45, three minutes later, having
spent 5,716. An 11,000 reservation returning 200 does not mean 11,000 of
daily headroom, and it certainly does not mean the 86,000 a suite needs.
Two probes after the run, with the daily bucket known to be at 99,600,
say why:

```
$ probe: requested_max_tokens=32768   (15:02Z)
status 200   x-ratelimit-remaining-tokens: 11907
$ probe: requested_max_tokens=11000   (15:03:39Z)
status 200   x-ratelimit-remaining-tokens: 11907
```

Both succeeded with the daily cap effectively full, and both held 93
tokens rather than the 32,805 and 11,037 that `max_tokens` asked for. The
worker's 429 six minutes earlier reported `Requested 1572` on a call whose
prompt was about that size and which sets no `max_tokens` at all. So the
daily counter is being charged something close to real usage, and the
14:57 reservation of 11,037 was against the per-minute bucket, which
refills in 60 seconds and gates nothing that matters. Phase 11 built the
gate on the belief that TPD reserves `max_tokens`; on today's evidence it
does not, and every phase since has been paying 11,000 tokens for a signal
that carries no information about whether a suite can run.

There is a cheap replacement and it is worth writing down for whoever
takes this next. `max_tokens` is capped at 32,768 on this model
(`status 400`, tried above), so no single request can reserve a suite's
worth. The only reliable pre-flight is the 429 itself: read `Used` out of
any rejected request, since a rejection charges nothing, and compare it to
the suite's measured cost before starting.

At `Used 99600` and a refill of 4,166.7 tokens per hour, a suite needing
86,157 needs `(99600 - 13843) / 4166.7 = 20.6` hours of accrual, so a
clean window opens around 11:35Z on 2026-08-09. Nothing may touch the key
before then, including probes.

### Step 6: tool calls per diagnose run

This is the deliverable, and it is n=5 rather than phase 11's n=24. Five
live diagnose runs completed today with neither answer key in the prompts:
three from the fixture recording at 14:30, two from the live suite at
14:58 before the cap hit. A sixth failed on 429 and a seventh never
started.

```
inc_01KZGWK5XHZ2ZV93R8F0G7BQ7X  latency_p95/target-orders    query_metrics, query_logs, submit_diagnosis
inc_01KZGWKATXW6JKB4QF8X60FB91  latency_p95/target-gateway   submit_diagnosis
inc_01KZGWKYE2J4W2NEEC6K6DVA9Q  error_rate/target-gateway    submit_diagnosis
inc_01KZGY4MX6H0TWN6Q28DPCFWW7  error_rate/target-payments   submit_diagnosis
inc_01KZGY4MXGN8M1S7GWCDB3263Q  error_rate/target-gateway    submit_diagnosis

submit_diagnosis: 5
query_metrics:    1
query_logs:       1
query_traces:     0
```

Phase 11's baseline, taken with both answer keys in place, over 24
diagnoses:

```
submit_diagnosis: 24
query_metrics:     5
query_logs:        5
query_traces:      0
```

One run in five read a tool before answering, against roughly one in five
in phase 11. On this sample the deletion did not move the rate, and n=5
cannot support a claim that it moved it in either direction. Two things it
does support. `query_traces` is still at zero, now across 29 live
diagnoses over three phases and two prompt versions, so the tool phase 10
built has never once been called by this model. And what the four
tool-free runs say changed completely: they used to name a fault from the
list at confidence 0.5 to 0.8, and now they restate the symptom they were
handed at confidence 0.0. The model was not diagnosing before and is not
diagnosing now; the difference is that it has stopped sounding like it is.

The four live incidents that reached a plan all proposed `restart_service`
at confidence 0.8, including the two `error_rate` ones that used to draw
`rollback_config` from the deleted bullet. Both of those resolved, which
is worth one caution: `error_spike` is an in-process flag on
target-payments, so a container restart clears it by accident. A green
tier action that happens to work is not the same as the right action.

### Defect 18: verify never compares p95 against its threshold

Found while reading the live latency incident that resolved with the toxic
still installed. `_probe_services_once` builds its threshold map keyed by
rule id and then looks it up by query name:

```python
thresholds = {r["id"]: ... for r in rules_cfg["rules"] ...}   # latency_p95, error_rate
for rule_id, promql in queries.items():                        # p95_latency, error_rate
    threshold = thresholds.get(rule_id)
    if value is not None and threshold is not None and value > threshold:
        over_threshold = True
```

`thresholds.get("p95_latency")` is `None`, so the latency comparison never
runs. `error_rate` works only because its rule id and its query name are
the same string. Pasted from the live run's own `verify.passed` event:

```
"metrics": {"p95_latency": 10000.0, "error_rate": null},
"over_threshold": false
...
"all_healthy": true
```

10,000ms against a 1,000ms threshold, reported healthy.
`nodes/verify.py:86` sets `passed = bool(probes["all_healthy"])`, so any
latency incident passes verification whatever the latency is. This is what
let `restart_service` close a latency incident, and it has been true since
phase 2.

Not fixed here. It changes what verify does to every live incident, and
this phase's whole point was to read one prompt change cleanly; fixing it
in the same commit would confound the next measurement the same way phase
12 said splitting the deletions would. It is a one-line change and it
should be the first item of the next phase, with a run that can measure it.

The half of the system that did work: both latency incidents carry
`[injected fault still present at verify]` in their summary, because the
`injected_fault_present` check is a separate, correct probe. The incident
closed wrongly and the record says so.

### Defect table

| #   | Severity | What                                                                                                                                                                    | Status                                            |
| --- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| 13  | medium   | Live diagnose reads database latency as a cache fault, so `latency` heals with `restart_dependency` and the toxic survives a passing verify                             | superseded by 18, symptom never reproduced        |
| 14  | medium   | `query_traces` searched recent traces, not slow ones, and reported no per-span timings                                                                                  | fixed (phase 10), 0 calls in 29 live diagnoses    |
| 15  | low      | The token cap was read as a per-calendar-day and then as a rolling 24h window; it is a bucket refilling at 4,167 tokens/hour                                            | bucket rate holds, the reservation model does not |
| 16  | high     | Live diagnose answers every `latency_p95` incident with `remove_toxic` without calling a tool, so `cache_outage` (paused `shop-redis`) never heals                      | closed, cause removed, replaced by 19             |
| 17  | high     | The worker's LangGraph Postgres checkpointer never reconnects after a dropped connection; the worker stays up, reports healthy, and escalates every incident it accepts | fixed (phase 13), pool + retry + healthcheck      |
| 18  | high     | Verify looks up the latency threshold by query name against a map keyed by rule id, so `over_threshold` is never set for p95 and any latency incident passes            | open, found phase 13, reproduced live and fixture |
| 19  | high     | With no answer key, live diagnose restates the symptom at confidence 0.0 and the plan node answers every incident with `restart_service`, so `latency` no longer heals  | open, found phase 13, n=5 live                    |

Four rows moved on evidence this phase, which is the difference from phase 12.

Defect 17 is fixed and has a test that fails without the fix.

Defect 16 is closed and replaced rather than carried. Its wording was
"answers every `latency_p95` incident with `remove_toxic` without calling
a tool", and that specific behaviour is gone: nothing in the prompts names
the toxic, and no live run this phase proposed `remove_toxic` at all. What
survived the deletion is the part underneath it, which is that diagnosis
mostly does not read evidence, and that is now defect 19 in its own words
with its own numbers.

Defect 13 is superseded by 18. Its symptom (`restart_dependency` on a
database toxic) never reproduced in phases 11, 12 or 13. The part of it
that is real, "the toxic survives a passing verify", turns out not to be a
diagnosis problem at all: verify cannot fail a latency incident.

Defect 14 stays open in the only sense that matters. The tool works and
has been called zero times in 29 live diagnoses across three phases.

Defect 15's bucket rate (4,166.7/hour) has now predicted four retry-after
strings to within 0.1%. The reservation half of it is wrong and is
corrected in step 5.

### README

The measured table is untouched: it is still phase 6 numbers from a
different model set, and this phase produced no MTTR that belongs in it.
`scripts/collect_live_numbers.py` was not run, because the live suite did
not pass and the brief said to leave the table alone in that case.

Two claims outside the table were false as written and are corrected. The
quickstart said fixture runs "heal all five scenarios"; four of five, since
`test_latency_heals` fails. "What this is not" said the remediation prompt
still carried its answer key and the re-measurement had not been taken;
both are now done, and the paragraphs say what the five live diagnoses
found instead of what phase 11's 24 found under a prompt that no longer
exists.

### Lint and unit tests

```
$ make lint
ruff + mypy clean, eslint clean, prettier: All matched files use Prettier code style!

$ make test
93 passed, 2 warnings in 0.68s          (pytest apps/core)
Test Files  8 passed (8), Tests 46 passed (46)   (vitest, console)
PASS: 9/9                                (opa test packages/policies)
```

93 rather than phase 12's 88: five new tests in
`apps/core/tests/test_checkpointer_health.py`.

The two mechanical checks from `scripts/gate.sh` that apply here:

```
$ git grep -In $'\xe2\x80\x94' -- . ':!plan' ':!PLAN.md' ':!scripts/gate.sh'
(no matches)
$ git grep -n "shell=True" -- apps/
(no matches)
```

### State this section leaves behind

- Branch `phase-13`, tagged `phase-13`. Nothing pushed, no remote touched,
  `v0.1.0` not tagged.
- `.env` restored byte-identical, verified by checksum:
  `4c9e677cd3d55f00a4396eff39230081` before and after, `MOCK_LLM=1`, and
  core-worker recreated from it.
- All five chaos toggles verified `fault_present: false` after the run.
- The fixture gate is red on one test, `test_latency_heals`, for the
  reason in step 4. Nothing else fails.
- The large-model key is at `Used 99600` of 100,000 as of 15:00:45Z and
  needs about 20.6 hours before a full live suite is worth starting, so
  around 11:35Z on 2026-08-09.
- Outstanding, in order: defect 18, which is one line and gates whether
  `latency` can ever fail verification; defect 19, which is what the model
  does without an answer key and needs a real suite to size; and the live
  suite itself, which no phase since 11 has completed.
