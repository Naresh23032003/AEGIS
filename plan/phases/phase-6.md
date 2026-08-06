# Phase 6 brief: Hardening, evidence pack, launch assets

Goal: everything green, measured numbers collected, the evidence pack export built, and the repo ready for a stranger.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. plan/06-milestones.md, "Phase 6" section
4. plan/07-review-and-launch.md, all of it
5. plan/02-contracts.md, "HTTP API" table row for evidence-pack

## Build order

1. Full e2e matrix: five scenarios on fixtures in CI, five live locally. Fix flakes properly (no retries-as-medicine). Time a cold clone to first heal and record it.
2. Evidence pack export: `GET /api/incidents/{id}/evidence-pack` returns a zip containing report.pdf and events.jsonl. The PDF: incident summary, full timeline, every action with policy decision and rule id, every approval and veto with signer fingerprint and signature, chain verification result, agent runs with model and cost. Sections carry EU AI Act mappings as subtitles: record-keeping (Article 12), human oversight (Article 14), serious incident report draft (Article 73). Generate with reportlab or weasyprint, styled plainly (this is a regulator document, not the console aesthetic). One e2e test downloads a pack and asserts the PDF opens and the jsonl chain re-verifies.
3. Collect real numbers from three live runs per scenario: MTTR, cost, autonomy level. These populate the README table and the MTTR badge.
4. README per the structure in plan/07, demo GIF recorded from the real UI, docs/architecture.md final diagram.
5. Demo video per the script in plan/07; LinkedIn drafts in docs/launch/ following CLAUDE.md writing rules.
6. Optional, only if everything above is done: chain-tamper demo button, second approver key flow.

## Gotchas

- The evidence pack reads only from Postgres (events, actions, approvals, agent_runs); it must work for any resolved or escalated incident with zero extra bookkeeping. If something is missing from the events, that is a phase 3 bug, fix it there.
- Frame the Act mapping honestly in the README: high-risk obligations apply from December 2027 (Digital Omnibus deferral); AEGIS demonstrates the runtime evidence shape early. No compliance claims, the word "aligned" not "compliant".
- Every number in README and launch copy must trace to a pasted run in the phase report.

## Exit ritual

Acceptance from plan/06 phase 6 including the stranger test. PHASE_6_REPORT.md with the cold-clone timing, live-run table, and evidence pack sample attached. Branch/tag phase-6, push, stop. The final full verification pass is run by the reviewer, not you (plan/07).
