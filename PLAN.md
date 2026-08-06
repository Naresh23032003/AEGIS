# AEGIS Build Plan

AEGIS is a self-healing incident operations platform. It watches a live demo system, detects injected faults, diagnoses them with a team of LLM agents, fixes low risk problems on its own, routes risky fixes through signed human approval, verifies the result, and replays every decision in a flight recorder UI. The headline demo: press an "Inject fault" button, watch agents heal the system in under 90 seconds, then scrub back through every decision they made.

This folder is the complete specification. It is written so that Claude Sonnet can execute the entire build without making architecture decisions. Every decision is already made. If a spec conflicts with your instinct, the spec wins. If a spec is silent, pick the simplest option that satisfies the acceptance criteria and record the choice in the phase report.

## How to use this plan (instructions for the executing model)

The plan is executed one phase per session, with a scoped reading list per phase. Do not read the whole plan/ folder at once; the briefs exist so each session loads only what that phase needs.

1. Read CLAUDE.md first. It contains repo conventions and writing rules that apply to every file you create.
2. Read plan/phases/phase-N.md for the current phase. It lists exactly which spec files and sections to read, in order. Read those and nothing else.
3. Build and test the phase against its acceptance criteria in plan/06-milestones.md.
4. Write docs/reports/PHASE_N_REPORT.md, commit, branch phase-N, tag, push, and stop for review. Never start the next phase in the same session.
5. Never invent new event types, DB columns, API routes, or catalog actions. Extend plan/02-contracts.md and plan/03-agents-and-policy.md first, in the same commit, if something is missing.
6. Each phase begins from a repo where the previous phase's tag passed review. If something from an earlier phase looks wrong, flag it in the report; do not silently rework it.

Current phase on a fresh start: check `git tag` for the highest phase-N, then execute phase N+1.

## Plan files

| File | Contents |
|---|---|
| plan/01-architecture.md | Locked stack, monorepo layout, runtime topology, ports, ADR summaries |
| plan/02-contracts.md | Event envelope, event catalog, database schema, HTTP and WS APIs |
| plan/03-agents-and-policy.md | Agent graph, prompts guidance, action catalog, risk tiers, OPA policy |
| plan/04-security.md | Signing, hash chain, executor sandbox, prompt injection defense |
| plan/05-frontend.md | Design system, screens, motion spec, 3D topology scene, fallback |
| plan/06-milestones.md | Seven phases with tasks, acceptance criteria, verification commands |
| plan/07-review-and-launch.md | Review checkpoints, e2e gate, README, demo video, LinkedIn assets |

## Positioning (context, not build work)

The AI SRE market is crowded in 2026 (Resolve AI, Datadog Bits AI, Traversal, Cleric, incident.io, PagerDuty). AEGIS does not compete on detection or scale. Its wedge is provable trust: a policy engine that physically blocks out-of-scope actions, Ed25519 signed approvals in a hash-chained audit log, and full incident replay. The tagline used in the README and launch assets: they sell resolution, AEGIS sells proof of resolution.

Primary goal: a hiring artifact for forward deployed engineer roles. Secondary goal: an open source repo credible enough to attract self-hosted design partners later. Both goals are served by the same build.

## Non-negotiable quality bars

- `docker compose up` from a clean clone brings up the entire system in under 5 minutes.
- The full demo works offline with MOCK_LLM=1 (recorded agent fixtures), no API key needed.
- All five chaos scenarios pass the e2e suite.
- No em dashes anywhere in the repo: docs, comments, commit messages, UI copy.
- Real measured numbers in the README (MTTR per scenario, cost per incident), not invented ones.
