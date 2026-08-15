# AEGIS

![AEGIS console: a stopped service is detected, diagnosed from metrics and logs, restarted and verified in 7 seconds; then an injected latency fault gets a restart that does nothing to it, and the incident closes with the fault still installed and the summary saying so](docs/media/demo.gif)

AEGIS is a self-healing incident operations platform. It watches a real
three-service system, detects injected faults with a plain rules engine,
diagnoses them with LLM agents reading live metrics, logs and traces,
fixes low-risk problems on its own, routes risky fixes through a signed
human approval, verifies the result, and replays every decision in a
flight-recorder UI.

Most self-healing demos sell the resolution. AEGIS sells the proof of
resolution: a hash-chained event log, signed approvals, and a
regulator-styled evidence pack for anything it touched.

## Quickstart

No API key, offline, deterministic. `MOCK_LLM=1` is the `.env.example`
default:

```
git clone https://github.com/Naresh23032003/AEGIS.git
cd AEGIS
cp .env.example .env
make up
```

Docker and Python 3.12 are the only prerequisites. `make up` provisions
its own `.venv` and npm workspace deps, builds the stack, and brings every
container up healthy, typically inside 2 minutes on a warm build cache.

Open <http://localhost:3000>, go to **chaos**, and press **inject fault**
on the **crash** card. That is the first act of the GIF above: the
topology turns the stopped service red, an incident card appears 13
seconds later when detection fires, and the heal itself took 7 seconds.

The second act is the **latency** card, and it is there because it does
not work. The agent proposes `restart_service` for a fault that is a
Toxiproxy toxic, restarting a service that was never down. The incident
closes 13 seconds after detection with the toxic still installed, and the
summary says so. Both acts come from one `make demo` run on fixtures; see
[What this is not](#what-this-is-not) for why the second one closes at
all. `make down` tears it all down.

## How it works

```
detect  ->  triage  ->  diagnose  ->  plan  ->  policy gate  ->  execute  ->  verify
 rules       LLM         LLM          LLM         OPA            Docker       probes
```

A rules engine detects, with no LLM in the path. A LangGraph agent loop
diagnoses and proposes an action from a closed catalog. OPA gates every
proposal by tier: green executes, yellow opens a veto window, red blocks
on an Ed25519-signed human approval. One process holding the Docker socket
executes. Every step is a hash-chained event, streamed live to the console
and replayable afterwards.

See [docs/architecture.md](docs/architecture.md) for the diagram and a
paragraph per layer, and [docs/adr/](docs/adr/) for the eight decisions
behind it.

## Proof, not just outcome

- **Closed action catalog.** Agents pick a `catalog_key` from a fixed,
  typed list ([catalog.yaml](apps/core/aegis/actions/catalog.yaml)). There
  is no path from an LLM response to a shell command, and the executor
  never imports LLM code.
- **Policy gate on every action.** [OPA](packages/policies/aegis.rego)
  evaluates tier, confidence and severity before anything runs. A
  below-confidence proposal is denied and the incident escalates to a
  human instead of guessing.
- **Signed human decisions.** Approvals and vetoes are Ed25519-signed in
  the browser. The server verifies but never holds a key that could forge
  one.
- **Hash-chained audit log.** Every event is `sha256(prev_hash ||
canonical_json(envelope))`, written in the same transaction as the row it
  describes. `GET /api/incidents/{id}/verify-chain` recomputes it, so
  tampering is detectable.
- **Evidence pack.** `GET /api/incidents/{id}/evidence-pack` returns a zip
  of a regulator-styled PDF (timeline, every policy decision and rule id,
  every signed approval, chain verification, agent runs and cost) plus
  `events.jsonl`. Sections are subtitled with the EU AI Act articles they
  map to (12, 14, 73). No compliance claim is made; high-risk obligations
  apply from December 2027, and this shows the runtime evidence shape
  early, not certification.

## Measured results on gpt-oss-120b, gpt-oss-20b and qwen3.6-27b

Not the model running now. Three live runs per scenario against the real
Groq API on that model set, pasted from
[PHASE_6_REPORT.md](docs/reports/PHASE_6_REPORT.md):

| Scenario           | Autonomy | MTTR (avg) | Cost/incident | Action                     |
| ------------------ | -------- | ---------- | ------------- | -------------------------- |
| latency            | auto     | 92s        | $0.0025       | `remove_toxic` (green)     |
| crash              | auto     | 61s        | $0.0015       | `restart_service` (green)  |
| error_spike        | auto     | 132s       | $0.0030       | `rollback_config` (yellow) |
| memory_leak        | auto     | 21s        | $0.0019       | `restart_service` (green)  |
| cache_outage (n=1) | auto     | 136s       | $0.0023       | `remove_toxic` (green)     |

On the current model none of the five reproduces inside 20%, and `latency`
does not heal at all. Read the table as a record of what that model set
did, not as what this repo does today.

Fixture runs (`MOCK_LLM=1`, deterministic, no API key) heal four of the
five in well under a minute each. That is the mode CI and the quickstart
run on. `latency` is the exception, for the reason below.

## What this is not

A production incident-response system. One docker-compose host, five
chaos scenarios, a free-tier LLM key with a daily quota this project
exhausted repeatedly. Kubernetes executor, Temporal, WebAuthn approvals
and a larger catalog are tracked as issues, not built here.

**Diagnosis quality is the honest weak point, and the prompts were hiding
how weak.** The diagnose prompt used to list all five injected faults by
mechanism; the remediation prompt named three of their fixes with the
parameter filled in. A model handed a symptom could match the list and
answer without reading anything. Both were deleted in phases 12 and 13.

Without them, over five live diagnoses on `llama-3.3-70b-versatile`: one
called `query_metrics` and `query_logs` before answering, four answered on
turn 1 with no tool call, and none called `query_traces`. That last number
is zero across 29 live diagnoses and three phases, so the evidence tool
built in phase 10 has never been called once. The tool-free runs used to
name a fault at confidence 0.8; they now restate the symptom at 0.0. The
model was not diagnosing before and is not diagnosing now. It has stopped
sounding like it is.

**`latency` no longer heals.** With the toxic's name gone from the prompt
the model proposes `restart_service`, which does nothing to a Toxiproxy
toxic, and the incident closes with the fault installed. It closes because
p95 is never compared against a threshold at all, and the reason is a
two-word mismatch. In
[rules.yaml](apps/core/aegis/detection/rules.yaml) the query is keyed
`p95_latency`; the rule that uses it has the id `latency_p95`. In
[tools.py](apps/core/aegis/agents/tools.py), line 309 builds the threshold
map keyed by **rule id**, line 320 iterates the **query keys**, so
`thresholds.get("p95_latency")` returns `None` and the comparison on line
328 is skipped for every latency reading ever taken. The probe reported
10,000ms against a 1,000ms limit and still returned `all_healthy: true`.

`error_rate` escapes this only because its rule id and its query key are
the same string. Latency has gone unchecked since phase 2, and that is why
`test_latency_heals` fails. It is left in, failing, on purpose.

Two things survive that. Verification separately re-checks whether the
injected fault is still in place, so those incidents carry `[injected
fault still present at verify]` in their summary and in the chained log.
Every action taken was a legal catalog action, policy-approved before it
ran. The system reports what it actually did, including the parts that did
not work. Full detail in
[FINAL_VERIFICATION.md](docs/reports/FINAL_VERIFICATION.md).

## Layout

`apps/console` (Next.js), `apps/core` (FastAPI api/worker/executor),
`apps/target` (the system that gets broken and healed),
`packages/contracts` (JSON Schema source of truth), `packages/policies`
(OPA/Rego), `deploy/` (compose stack). Full layout in
[plan/01-architecture.md](plan/01-architecture.md).

## Development

```
make lint test      # ruff + mypy + eslint + prettier + pytest + opa test
make e2e            # scenario suite against a running stack (make up first)
make e2e-live       # same, with MOCK_LLM=0 in .env
```

Built from the specification in [PLAN.md](PLAN.md) and [plan/](plan/), one
phase at a time. Each phase's report is in [docs/reports/](docs/reports/).
