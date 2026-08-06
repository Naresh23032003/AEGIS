# Phase 3 brief: Policy, tiers, approvals, security

Goal: the trust layer. OPA gates every action, yellow tier gets a veto window, red tier parks on a signed approval, the chain is verifiable, and all five scenarios heal.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. plan/06-milestones.md, "Phase 3" section
4. plan/03-agents-and-policy.md, "Risk tiers", "OPA policy", "Action catalog", "Chaos scenarios" sections
5. plan/04-security.md, all of it
6. plan/02-contracts.md, "HTTP API" (approvals, veto, keys, verify-chain, catalog) and the approval/veto event types

## Build order

1. packages/policies: the six Rego rules with an opa test each. Worker calls OPA per proposal, emits action.policy_checked.
2. Gate node completion: green auto-path through OPA; yellow veto window (30s timer, veto cancels, timeout executes); red LangGraph interrupt parking the run, resumed by POST /approvals, 15 minute unanswered escalation.
3. Signing: POST /keys, PyNaCl verification on approve/reject/veto, ts staleness check, signatures embedded in events. An integration test signs with PyNaCl directly (no browser yet).
4. Remaining green/yellow catalog actions in the executor (restart_dependency, scale_service, rollback_config) plus red stubs that execute against the demo stack (flush_queue, restart_database).
5. Heal error_spike, memory_leak, cache_outage live; record fixtures; extend e2e to all five.
6. GET /incidents/{id}/verify-chain and the chain tamper test.
7. Adversarial e2e: injected log line must never yield a flush_queue proposal.

## Gotchas

- The interrupt resume path must survive worker restart while parked (checkpoint holds the interrupt); test it.
- Veto window timing belongs in the worker, not the DB; but closes_at goes in the event so the UI can render the countdown from data.
- OPA input includes actions_executed; count executed actions per incident from the DB, not from graph state.
- Yellow timeout executing while a veto arrives simultaneously: take a row lock on the action, first writer wins, loser gets 409.

## Exit ritual

Acceptance from plan/06 phase 3, PHASE_3_REPORT.md with pasted opa test and e2e output for all five scenarios, branch/tag phase-3, push, stop.
