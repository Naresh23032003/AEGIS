# Phase 10 brief: Diagnosis evidence discipline, then finish the numbers

Goal: one scoped attempt at defect 13, then finish the README either way. This phase ends shippable regardless of whether the attempt succeeds, so there is no third live round trip.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. docs/reports/FINAL_VERIFICATION.md, the "Phase 9" section, specifically the defect 13 trace
4. apps/core/aegis/agents/prompts/diagnose.md and apps/core/aegis/agents/tools.py (the trace and metric tools)

## The reviewer's read on defect 13

The model blamed the cache for 1500ms of latency sitting between target-orders and its database. The evidence that would have distinguished them was available and apparently unused: a span timing on the orders to shop-db call. This is an evidence discipline problem, not a reasoning ceiling, so it gets exactly one attempt at the prompt and tool layer. No model swap, no new tools, no change to routing or policy.

## Build order

1. One diagnose prompt iteration, aimed at evidence rather than at the answer. Require the hypothesis to name which tool output supports it, and require that before blaming a dependency the model checks span timings on the call to that dependency. Do not name the latency scenario, the toxic, or Toxiproxy anywhere in the prompt; a prompt that recognises the test rather than the evidence is worse than the current failure and will be rejected in review.
2. If `query_traces` returns only trace ids and durations without per-span service timings, extend it to include the slowest spans with their service names. That is a tool fidelity fix, in scope, and note it in the report.
3. `MOCK_LLM=1 make e2e` (18 tests) must stay green. Re-record any latency fixtures the prompt change invalidates.
4. `make e2e-live`, first thing on a fresh large-model budget. Record the result whether it is 18/18 or 17/18. One attempt only. If `test_latency_heals` still fails on `fault_present=True`, that is the answer and the phase continues to step 5 with it.
5. Unconditionally now, regardless of step 4: run `scripts/collect_live_numbers.py --scenarios error_spike,cache_outage` for three samples each, update the README's measured table with the new rows, drop the `cache_outage (n=1)` caveat, and recheck every remaining row against the 20% band. The phase 9 gate on a clean live suite is lifted; the numbers are worth having either way and the budget allows both runs on one key.
6. README honesty pass, written to match whichever outcome step 4 produced. If latency still misdiagnoses, say so plainly in "What this is not": that on the free-tier model the latency scenario is diagnosed as a cache fault roughly as often as not, that the action taken is legal, reversible and policy-gated, and that the incident is labelled `injected fault still present at verify` when it happens. Do not bury it and do not dramatise it. That label existing is a strength, so let it read as one.
7. Append a "Phase 10" section to docs/reports/FINAL_VERIFICATION.md with pasted output, and close or restate defect 13.

## Gotchas

- Per phase 9, the token limit is per model, not per key: the suite costs about 77,000 large-model tokens and the collection about 18,000, so both fit one key in one day. Run the suite first.
- Do not touch the executor, chain, signing, evidence pack, detection episodes, or the Redis split.
- If the prompt iteration makes any other scenario worse, revert it and record that. A net loss is a failed attempt, not a trade.

## Exit ritual

Branch phase-10 off phase-9, conventional commits, tag phase-10, do not push, do not tag v0.1.0. Stop.
