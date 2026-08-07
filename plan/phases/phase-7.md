# Phase 7 brief: Release fixes

Goal: close the three open defects from docs/reports/FINAL_VERIFICATION.md, re-verify live, refresh the README numbers, and hand the repo back clean for the v0.1.0 decision. The reviewer has already made the design decisions; they are in the amended specs. Do not relitigate them.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. docs/reports/FINAL_VERIFICATION.md, sections for defects 3, 5, 6 and "Not verified"
4. plan/03-agents-and-policy.md, "Detection" section (amended)
5. plan/05-frontend.md, "Frontend data layer" and the topology fallback paragraph (amended)

## Build order

1. Defect 3, detection episodes. Implement the amended dedupe: one incident per (rule, service) per continuous firing episode; re-opening requires at least one clean evaluation since the incident was created, regardless of status. e2e test: inject error_spike for 60 seconds, assert exactly one incident opens per (rule, service) pair for its duration; a second injection after clearing opens a new one.
2. Defect 5, store seeding. On WS connect and reconnect the Zustand store seeds from REST (open incidents + full event log for anything awaiting_approval) before live-tailing; ApprovalOverlays changes only in what it selects. e2e test: park a red-tier action, reload the page, approve from the drawer that now renders, assert resolution. Same commit: approval drawer takes initial focus on mount and traps focus (vitest cases for both).
3. Defect 6, static 3D under reduced motion. Gate the idle ticker and ambient pulse on the reduced-motion preference even when ?view=3d forces the scene. Extend the existing Playwright reduced-motion check: forced 3D canvas pixels identical across a 4s idle gap.
4. Full re-verify: make lint test, MOCK_LLM=1 make e2e (now 18 tests), then make e2e-live on the fresh key. FINAL_VERIFICATION.md predicts 15/15 live fits the free-tier daily budget once defect 3 is fixed; if it still exhausts quota, stop and report rather than substituting models.
5. Refresh numbers: rerun scripts/collect_live_numbers.py for error_spike and cache_outage (3 samples each), update the README table and its n=1 caveat, and drop the README's "inject: latency" phrasing check one more time against the real screen.
6. Update docs/reports/FINAL_VERIFICATION.md defect table statuses and append a short phase 7 addendum with pasted output for every fix.

## Gotchas

- The episode rule lives in the detection loop, not in SQL alone: track "seen clean since incident open" per (rule, service) in the worker's runtime object, and rebuild that state from the DB on worker start so a restart does not double-open.
- Store seeding must be idempotent against the live tail: events arriving twice (REST seed + WS overlap) must fold identically. Dedupe by event id in the store.
- Do not touch the veto window, executor, chain, or evidence pack code paths; nothing in this phase changes them.

## Exit ritual

PHASE_7_REPORT.md is the addendum in step 6. Branch phase-7 from phase-6, conventional commits, tag phase-7, do not push, do not tag v0.1.0, stop. The release decision is the reviewer's.
