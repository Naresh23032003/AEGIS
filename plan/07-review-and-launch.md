# 07. Review protocol and launch

## Review loop (Sonnet builds, Fable reviews)

After each phase, the executing model stops and the review model checks the tagged commit against this protocol. Fixes happen on the same phase branch; the tag moves only after the review passes.

Per-phase review checklist (applied every time):

1. Phase report exists, honest about deviations, includes pasted test output (not summarized).
2. Acceptance criteria from plan/06 re-run from the report's own commands, not trusted from prose.
3. Contracts discipline: no event types, routes, columns, or catalog keys that are absent from plan/02 and plan/03 without a same-commit spec update.
4. Security spot-checks: no shell=True, no Docker socket outside executor, no LLM imports in executor, quarantine wrapping present on every diagnosis tool, no secrets in code or logs.
5. Writing rules: zero em dashes repo-wide (`grep -rn $'—' . --exclude-dir=node_modules --exclude-dir=.git`), banned-word scan per CLAUDE.md, commit messages conventional.
6. Frontend phases: design-system/MASTER.md checklist walked screen by screen; contrast and focus states verified; no purple gradients, no emoji icons.
7. Dead code and TODOs: none left without a linked issue note in the phase report.

## Final full verification (run by the reviewer, not the builder)

After phase 6 passes its own review, the reviewer runs the complete matrix independently:

1. Stranger test, literally: clean clone, follow only the README, time to first heal, screen-record it. Any step needing knowledge outside the README fails the release.
2. `make e2e` (all five scenarios, fixtures) and `make e2e-live` from scratch; MTTR numbers must be within 20% of the README's claims.
3. Kill core-worker during a live red-tier park; approve after restart; the run must resume and heal.
4. Security sweep: shell=True grep, Docker socket mounts, executor import graph, quarantine wrapping, secret leakage in logs, chain tamper detection, adversarial injection e2e.
5. Evidence pack: download for two incidents (one auto, one approved), verify PDF contents against the event log by hand, re-verify the jsonl chain.
6. Full writing sweep: em dash grep, banned words, README numbers traced to phase reports.
7. UI walkthrough on both renderers (3D and forced 2D), keyboard only, then reduced motion.

Defects found here reopen phase 6. The release tag moves only when this list is clean.

## README structure (write in phase 6)

1. Demo GIF (inject -> heal, under 20 seconds, recorded from the real UI).
2. One paragraph: what AEGIS is, the trust wedge, "they sell resolution, AEGIS sells proof of resolution".
3. Measured results table: per scenario MTTR, autonomy level, cost per incident (live-LLM numbers).
4. Quickstart: three commands, no API key path first (MOCK_LLM), live-LLM path second.
5. Architecture diagram + one paragraph per layer, linking to ADRs.
6. Security model section (signing, chain, sandbox, policy) kept short and concrete.
7. What this is not: honest paragraph noting demo scale and the production path items from plan/04.

## Demo video script (60-90s, no voiceover needed, captions only)

1. (0-5s) Title card: AEGIS. Self-healing operations with proof.
2. (5-15s) Ops console healthy: topology breathing, metrics strip.
3. (15-25s) Chaos panel, click "Inject: DB latency". Caption: breaking production on purpose.
4. (25-45s) Cut to console: incident card springs in, loop ring advancing, agent orbs converge, agent.step cards streaming. Caption: agents diagnose from live traces and logs.
5. (45-55s) Yellow-tier veto card with countdown; let it execute. Caption: risky actions wait for a human; signed, policy-gated.
6. (55-70s) Node flips green, MTTR counter stops. Caption with the real number.
7. (70-90s) Flight recorder scrub, chain-verified badge close-up. Caption: every decision replayable, every approval signed. End card: repo URL.

## LinkedIn assets (drafts in phase 6, docs/launch/)

- Main post: business-outcome framing, the measured MTTR number, the video attached, no hashtag walls (3 max), no em dashes, written per CLAUDE.md voice rules.
- Architecture image: single dark-theme diagram matching the console aesthetic.
- Follow-up post a week later: "what building it taught me" write-up linking the ADRs.

## GitHub presentation

- Repo: github.com/Naresh23032003/AEGIS, single author, default branch main, phase branches merged with merge commits (history shows the arc).
- Badges: CI status, license (Apache-2.0), and the measured MTTR as a static badge.
- Issues seeded with 5-8 genuine future items (WebAuthn approvals, Kubernetes executor, Temporal migration) so the repo looks alive.
- Releases: v0.1.0 tagged at launch with the demo video linked.
