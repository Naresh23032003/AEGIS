# Phase 13 brief: Finish the deletion, fix the checkpointer, then measure once

Goal: everything that must be true before a live run is worth taking, done in one pass, then one run that measures it. This is the last build phase.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. docs/reports/FINAL_VERIFICATION.md, the Phase 12 section
4. apps/core/aegis/agents/prompts/plan_remediation.md
5. apps/core/aegis/agents/graph.py and the AsyncPostgresSaver setup it uses

## The reviewer's decisions

Phase 12 was right to leave plan_remediation.md alone for attribution, and that reason has since expired: the diagnose deletion was never measured either, so there is no baseline to protect. Both blocks come out now, in one commit each, and the single live run at the end measures the pair. Splitting them costs a second 21 hour token window to separate two effects that will be reported together anyway.

Defect 17 is a real bug and it is the ironic one: a self-healing platform whose own worker cannot recover from a dropped connection, stays up, reports healthy, and escalates every incident it accepts. Fix it, and fix it in the code rather than by restarting containers, because it is also making suite runs unreproducible.

## Build order

1. **plan_remediation.md.** Remove the three bullets that name a scenario's fix and its parameter (`orders_shopdb_latency` by name, restart_service for a stopped process, rollback_config for target-payments error rates). Remove the catalog table's condition column where it encodes the same mapping; the table keeps catalog_key, tier, and what the action does, which is the executor's contract rather than an answer. What stays: the output contract, the confidence guidance, and the rule that an empty plan is not an answer. Apply the same three tests phase 12 used to diagnose.md, and report what you found.
2. **Defect 17.** Give the checkpointer a connection that recovers: an `AsyncConnectionPool` rather than a single connection, or an explicit reconnect on `OperationalError` with a bounded retry. The worker must not report healthy while its checkpointer is dead, so the health check has to exercise the checkpointer, not just the process. Add a test that closes the connection underneath a running graph and asserts the next incident still completes.
3. **Re-record the three poisoned fixtures** (`error_spike_target-gateway/diagnose_1.json`, `latency_target-gateway/diagnose_1.json`, `latency_target-orders/diagnose_1.json`) against the current prompts, before the suite, since they cost about 3,000 large tokens each. Any other fixture whose `diagnose_1` names a cause on turn 1 with no tool call gets the same treatment; check all of them and report the list.
4. `MOCK_LLM=1 make e2e`, 18/18 in a single pass, on a machine given room to hold the stack still. If Docker wedges, fix the machine and rerun rather than reporting a partial.
5. **One live run.** Gate with a single 11,000 token reservation and nothing more; phase 12 lost 30,041 tokens to a second probe. Make sure only one pytest process can touch the stack. Then `make e2e-live`, once.
6. **Report the tool call counts per diagnose run**, in phase 11's format, next to the pass or fail. That table is the deliverable of this phase. Phase 11's baseline, taken with both answer keys in place, was `submit_diagnosis 24, query_metrics 5, query_logs 5, query_traces 0`. A suite that scores worse while actually reading evidence is the better outcome and must be reported as one.
7. If the live suite passes, run `scripts/collect_live_numbers.py --scenarios error_spike,cache_outage`, three samples each, and update the README table. If it does not pass, leave the table alone and say why.
8. Update defects 13, 14, 16, 17 against evidence, rewrite "What this is not" to match, and append a Phase 13 section with pasted output.

## Budget reality

The suite costs about 86,000 large-model tokens and the bucket refills at 4,167 per hour, so one attempt needs roughly 21 hours of accrual on an untouched key. Steps 3 and 5 together need about 95,000. If the operator has moved to a paid Groq tier, say so in the report and run without the wait. Otherwise start the run at the top of a clean window and let nothing else touch the key first.

## Do not

- Do not swap the model. If llama-3.3-70b cannot diagnose without an answer key, that is the finding.
- Do not touch the executor, policy, chain, signing, evidence pack, detection episodes, or any assertion.
- Do not re-add either block in softened form, in a tool description, or in the state object.

## Exit ritual

Branch phase-13 off phase-12, conventional commits, tag phase-13, do not push, do not tag v0.1.0. Stop.
