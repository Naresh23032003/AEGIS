# 06. Milestones

Seven phases. Each ends with: all listed acceptance criteria passing, docs/reports/PHASE_N_REPORT.md written (what was built, deviations from spec, test output pasted, open questions), a conventional-commit history, git tag `phase-N`, push to origin. Then stop for review. Do not begin the next phase in the same session as a review request.

Global commands (Makefile targets to create in phase 0):

```
make up            # docker compose up -d --build
make down          # compose down -v
make contracts     # regenerate types from JSON Schema
make test          # unit tests (python + ts) + opa test
make e2e           # scenario suite against a running stack (MOCK_LLM=1)
make e2e-live      # same with real LLM
make record-fixtures SCENARIO=x
make lint          # ruff + eslint + prettier check
```

## Phase 0: Skeleton (target: 1-2 days)

- Monorepo layout from plan/01, all directories, package manifests, tooling configs (ruff, mypy, eslint, prettier, tsconfig).
- packages/contracts with the event envelope, IncidentState, ActionProposal schemas and working codegen.
- docker-compose.yml with every service defined; target services can be hello-world stubs, but postgres, redis, opa, toxiproxy, lgtm must be real and healthy.
- Makefile, .env.example, CI workflow running lint + test + opa test on push.
- docs/adr/ADR-001..008 written from the summaries in plan/01.
- CLAUDE.md at repo root (copy from this planning folder, adjust paths).

Acceptance: `make up` from clean clone -> all containers healthy in < 5 min; `make lint test` green in CI.

## Phase 1: Target system + telemetry + detection (target: 3-4 days)

- Build gateway, orders, payments (FastAPI each, ~150 lines): realistic endpoints (create order -> payment -> db write through Toxiproxy; cache reads through redis), healthz on each, OTel auto-instrumentation exporting to lgtm.
- loadgen container producing steady mixed traffic (~5 rps).
- Toxiproxy proxy configured orders -> shop-db at compose startup.
- Fault hooks: payments error_spike flag file + memory_leak endpoint; chaos endpoints in core-api implementing all five scenarios (inject + clear).
- Detection loop with rules.yaml, incident creation, hash-chained event writes, Redis stream publishing, `/incidents` + `/incidents/{id}/events` + `/ws/events` live.

Acceptance: inject each of the five scenarios via curl -> incident.detected event appears on the WS within 30s and in Postgres with a valid chain; Grafana shows traces from all three target services; clearing faults returns metrics to baseline.

## Phase 2: Agent loop end to end (target: 4-5 days)

- LangGraph graph with all nodes per plan/03, Postgres checkpointing, heartbeats, structured outputs against contracts.
- Diagnosis tools (Loki, Prometheus, Tempo, container stats) with quarantine wrapping and truncation per plan/04.
- Executor service with the full catalog and hardened mapping (green tier actions only need to work this phase).
- Real-LLM run heals `latency` and `crash` scenarios fully autonomously.
- aegis.llm wrapper + fixture recording; record fixtures for both working scenarios; MOCK_LLM=1 replays them deterministically.
- Supervisor quarantine on simulated agent timeout (unit-tested with a stubbed hung node).

Acceptance: `make e2e` passes latency + crash on fixtures; `make e2e-live` heals both with real LLM, MTTR < 150s; killing core-worker mid-run and restarting resumes the run from checkpoint (write this as a test).

## Phase 3: Policy, tiers, approvals, security (target: 3-4 days)

- OPA integration with the six rules + tests; action.policy_checked events.
- Veto window flow (yellow) and approval interrupt flow (red) with LangGraph interrupts parking runs.
- Ed25519: /keys, signed approve/reject/veto verification, signatures in events.
- Remaining three scenarios (error_spike, memory_leak, cache_outage) working live and recorded as fixtures.
- Adversarial e2e case (log-based injection attempt never yields flush_queue).
- verify-chain endpoint.

Acceptance: all five scenarios pass `make e2e`; a red-tier action visibly parks until an approval signed by a registered key arrives (integration test signs with PyNaCl); tampering with a stored event makes verify-chain report the break; OPA denies a below-confidence proposal and the event trail shows it.

## Phase 4: Console, 2D complete (target: 5-6 days)

- Install ui-ux-pro-max into the repo; write design-system/MASTER.md from plan/05.
- All five screens with the React Flow topology (the 2D fallback is the primary implementation this phase), WS store, replay scrubber, approval/veto overlays with signing, loop ring component, cmdk palette.
- Empty states, loading states, reconnect behavior.

Acceptance: with MOCK_LLM=1, a full demo runs entirely from the UI: inject from chaos panel -> watch feed + topology react -> veto or approve where prompted -> incident resolves -> open flight recorder and scrub the replay -> chain badge verified. Keyboard-only pass works; reduced-motion pass shows no animation; Lighthouse accessibility >= 90 on all routes.

## Phase 5: 3D scene + metrics + polish (target: 4-5 days)

- R3F topology per plan/05 behind the shared useTopologyState hook, with automatic fallback wiring.
- Metrics page. MTTR ticker strip. Camera choreography on fault. Bloom, DPR cap, demand frameloop, hidden-tab pause.
- Motion polish pass over every transition against the design-system checklist.

Acceptance: 3D scene holds 60fps on an M-series MacBook with an active incident (measure with the R3F perf monitor, paste numbers in the report); WebGL-disabled browser lands on 2D automatically with no error flash; `?view=2d` works; reduced-motion disables idle animation.

## Phase 6: Hardening + evidence pack + launch assets (target: 4-5 days)

- Full e2e matrix green (fixtures + live), cold-clone timing measured, flaky test burn-down.
- Evidence pack export per plan/phases/phase-6.md: GET /incidents/{id}/evidence-pack, PDF + events.jsonl zip with EU AI Act section mappings (Articles 12, 14, 73), tested e2e.
- README per plan/07 with the demo GIF at top; docs/architecture.md with final diagram; metrics table with real measured MTTR and cost numbers from live runs.
- Demo video recorded per the script in plan/07; LinkedIn post drafts.
- Optional if time remains: chain-tamper demo button, second approver key flow.

Acceptance: a stranger with Docker and no API key can clone, `make up`, open localhost:3000, press inject, and watch a heal within 5 minutes of cloning. That sentence is the release gate. Additionally: downloading an evidence pack for a resolved incident yields a valid PDF whose event log re-verifies against the chain.

## Sequencing rule

If any phase overruns by more than 50%, cut scope inside the phase (drop optional items, drop a scenario to three) rather than borrowing time from phase 4 or 6. The demo-critical path is: phase 2 loop, phase 4 UI, phase 6 README.
