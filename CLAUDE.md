# CLAUDE.md - AEGIS repo conventions

You are building AEGIS from the specification in PLAN.md and plan/. Decisions are already made there; do not redesign. When the spec is silent, choose the simplest thing that passes the phase's acceptance criteria and note the choice in the phase report.

## Working rules

- Work one phase at a time. Read only CLAUDE.md, your phase brief (plan/phases/phase-N.md), and the sections it lists. Stop after tagging a phase; do not start the next in the same session.
- Never invent event types, API routes, DB columns, or catalog actions. Update plan/02 or plan/03 in the same commit if an addition is unavoidable, and flag it in the phase report.
- Contracts are generated from packages/contracts JSON Schema. Never hand-write a duplicate Pydantic model or TS type for a shared shape.
- The executor never imports LLM code. Diagnosis tool outputs are always quarantine-wrapped. No shell=True anywhere in the repo.
- Tests accompany the code in the same commit, not in a cleanup pass. Every OPA rule has an opa test. Every chaos scenario has an e2e test.
- MOCK_LLM=1 must keep working from phase 2 onward; CI runs on fixtures only.

## Git

- Conventional commits: feat:, fix:, test:, docs:, chore:, refactor:. Scope by app, e.g. `feat(core): veto window state machine`.
- Small commits, each leaving the repo green. Phase branches named phase-N, merged to main after review, tag phase-N on the merge commit.
- Author: Naresh (single author). Never mention AI, Claude, or code generation in commits, comments, or docs.

## Writing rules (docs, comments, UI copy, commits)

- No em dashes anywhere. Use commas, periods, or parentheses.
- Banned words: delve, leverage, harness, seamless, robust, comprehensive, cutting-edge, streamline, foster, bolster, pivotal, holistic, landscape, realm, tapestry, testament, synergy, game-changing, revolutionize, unlock, unleash, "it's important to note", "in conclusion", "in today's fast-paced world".
- Vary sentence length; no three consecutive sentences with the same shape. Prefer specific numbers over adjectives ("heals in 47s" not "heals rapidly").
- README and launch copy: plain, concrete, measured claims only. Every number must come from an actual run.
- UI copy: short, mono-spaced for data, sentence case, no exclamation marks.

## Frontend

- Follow design-system/MASTER.md (created in phase 4 from plan/05). The anti-pattern checklist there is a review gate, not a suggestion.
- Lucide icons only. No emojis in UI. No purple/pink gradients. prefers-reduced-motion respected everywhere including the 3D scene.
- All live data flows through the single WebSocket Zustand store; components select, never fetch live data ad hoc.

## Python

- Python 3.12, ruff + mypy strict on apps/core. FastAPI with async throughout. Pydantic v2 generated models from contracts.
- No global mutable state outside the worker's explicit runtime object. Heartbeat every 10s from running agent nodes.

## Verification habit

Before declaring any task done: run `make lint test`, run the relevant `make e2e` subset, and paste real output into the phase report. Claims without pasted output fail review.
