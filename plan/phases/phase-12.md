# Phase 12 brief: Remove the answer key from the diagnose prompt

Goal: find out whether AEGIS diagnoses or pattern-matches. This is the experiment the whole project rests on, and it is one deletion plus one live run.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. docs/reports/FINAL_VERIFICATION.md, the Phase 11 section
4. apps/core/aegis/agents/prompts/diagnose.md

## What the reviewer found

diagnose.md has carried this since phase 2 (commit e7f8b2e):

> Known fault patterns in this system: a proxy adding latency between orders and its database; a service process stopped or crash-looping; a bad feature flag causing elevated error rates; unbounded memory growth ending in an OOM kill; a paused cache dependency.

That is the five chaos scenarios, listed by mechanism, in the prompt. The model receives "latency_p95 on target-orders" from triage, matches the first item, and submits in 464ms without calling a tool. Phase 11's zero `query_traces` calls across 24 diagnoses are not the model being lazy; the answer is already in its context and no evidence is needed to produce it. It also explains defect 16 exactly: `cache_outage` fires the same `latency_p95` rule, matches the same list item, and gets `remove_toxic` for a toxic that was never installed.

The README says agents diagnose from live traces and logs. With that block present the claim is not true, and anyone who opens diagnose.md on GitHub can see it. So the block goes, and whatever happens next is the real result.

## Build order

1. Delete the "Known fault patterns in this system" paragraph from diagnose.md. Nothing replaces it. The workflow section stays, since it teaches method rather than answers: which tool answers which question, and that slowness needs traces before a cause is named. Read the whole prompt afterward and remove any other sentence that names a specific injected fault, a container by role in a scenario, or a catalog action as the answer to a symptom. Do the same read of triage.md, plan_remediation.md and verify.md and report what you found in each, even if nothing.
2. `MOCK_LLM=1 make e2e` must stay green at 18/18. Fixtures replay recorded model turns, so they should be unaffected; if any fixture was recorded off the answer key and now misleads, re-record it and say so.
3. `make e2e-live`, once, on a budget that can actually hold it. Phase 11 measured the real numbers: the suite costs about 86,000 large-model tokens and the bucket refills at 4,167 per hour, so it needs roughly 21 hours of accrual on an untouched key. Confirm with a real 11,000-token reservation before starting, per phase 11's gate. Record the result whatever it is.
4. For every diagnose run in that suite, report the tool call counts (the phase 11 breakdown format) alongside the pass or fail. The tool counts are the actual measurement this phase exists to take. A suite that scores worse but reads evidence is a better result than phase 11, and should be reported as one.
5. Update defects 13, 14 and 16 against what the run shows, and rewrite the README's "What this is not" to match. If diagnosis quality drops without the answer key, say so plainly and keep the numbers honest.
6. Append a Phase 12 section to docs/reports/FINAL_VERIFICATION.md with pasted output.

## Do not

- Do not re-add the fault list in any softened form, and do not move it into a tool description, the triage prompt, or the state object. If it needs to be said that the system has five known faults, it does not.
- Do not swap the model. If `llama-3.3-70b-versatile` cannot diagnose without the answer key, that is a finding worth publishing, not a problem to configure around.
- Do not change tools, policy, the executor, or any assertion.

## Housekeeping

Tags `phase-10` and `phase-11` were never created despite both reports claiming them. Create them on their report commits (`d35d4f2` and `4ddceae`) before starting.

## Exit ritual

Branch phase-12 off phase-11, conventional commits, tag phase-12, do not push, do not tag v0.1.0. Stop.
