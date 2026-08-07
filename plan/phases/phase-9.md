# Phase 9 brief: Split the Redis instances, harden the live path

Goal: fix one architectural defect the live run exposed, make three e2e tests survive live model variance, then one clean live run. This is the last phase before v0.1.0.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. docs/reports/FINAL_VERIFICATION.md, the "Live verification" section (all of it)
4. plan/01-architecture.md, "Runtime topology" table (amended)
5. plan/03-agents-and-policy.md, "Action catalog" section

## Context the reviewer owns

The single Redis serving both the demo shop cache and the AEGIS event stream was a spec mistake in plan/01, not a build mistake. It gave `restart_dependency` a path to restart AEGIS's own event bus while an incident was in flight, which is where the `failed to publish event` lines and probably the 15 minute stall came from. The fix is a spec amendment, already made below.

## Build order

1. Split Redis into two containers: `shop-redis` (demo cache, the only one `clear_cache` and `restart_dependency` may touch) and `aegis-redis` (event stream, not in the action catalog at all, not reachable by any agent). Update compose, .env.example, REDIS_URL usage, and plan/01's topology table in the same commit. Add an executor-level guard: any catalog action naming a container outside the demo target set is rejected before it reaches Docker, with a unit test.
2. Make three tests robust to live model variance without weakening what they prove:
   - `test_latency_heals` and the other scenario tests: assert the incident resolved AND the injected fault is actually gone (query Toxiproxy / the fault flag directly), instead of asserting one exact catalog_key. A heal that leaves the fault in place must fail.
   - `test_veto_during_the_window_escalates_instead_of_healing`: stop depending on a live model producing a yellow action. Seed a yellow-tier action the same way the red-tier approval test seeds its own, so the test exercises the veto window rather than the model.
   - Keep the adversarial, approval, chain, evidence pack and reduced-motion tests exactly as they are.
3. Verify node: leave the probe logic alone, but record in the incident summary whether the originally injected fault was still present at verification time when the chaos API knows (test-only signal, not agent input). This turns "verify passed with the toxic still in place" into something visible rather than something a reader has to trust.
4. Full re-verify: `make lint test`, `MOCK_LLM=1 make e2e` (18 tests), then `make e2e-live` on a fresh daily budget, first thing, nothing else run before it. Target 18/18. If a scenario still fails on live model quality rather than infrastructure, record which and stop; do not substitute a model, do not loosen an assertion to make it pass.
5. If and only if the live suite passes: `scripts/collect_live_numbers.py --scenarios error_spike,cache_outage`, three samples each, then update the README table and drop the n=1 caveat. Recheck every remaining row against the 20% band.
6. Append a "Phase 9" section to docs/reports/FINAL_VERIFICATION.md with pasted output for every step, and update the defect table.

## Gotchas

- The two Redis containers need distinct hostnames everywhere, including the loadgen and the target services; grep for `redis:6379` and fix every hit rather than aliasing.
- Do not change the veto window, chain, signing, evidence pack, or detection episode code. Nothing in this phase touches them.
- The error_spike case where plan_remediation proposed no action at all is a prompt quality issue. One prompt iteration is in scope (make the available catalog keys and the expected output shape harder to miss); a model swap is not.

## Exit ritual

Branch phase-9 off phase-7, conventional commits, tag phase-9, do not push, do not tag v0.1.0. Stop.
