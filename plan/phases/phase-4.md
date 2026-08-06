# Phase 4 brief: Console, 2D complete

Goal: the full product UI, working end to end against MOCK_LLM=1, with the React Flow topology as the primary renderer. The 3D scene waits for phase 5.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. plan/06-milestones.md, "Phase 4" section
4. plan/05-frontend.md, all of it (skip only the "Topology scene (R3F)" section internals; do read its fallback paragraph, you are building that fallback as the primary now)
5. plan/02-contracts.md, "Event catalog", "HTTP API", "WebSocket" sections

## Build order

1. `npx ui-ux-pro-max-cli init --ai claude` in the repo. Write design-system/MASTER.md from the tokens and rules in plan/05. Every screen below gets checked against it before commit.
2. Data layer first: WS client with reconnect/backoff, Zustand store, replay-mode source swap, `useTopologyState()` hook. This hook is shared with phase 5; keep it renderer-agnostic (nodes, edges, statuses, active agents).
3. Ops console: incident feed with spring entry, loop ring component (standalone, tested per state), detail panel streaming agent.step cards, metrics strip with count-up.
4. Topology (React Flow): fixed grid layout, status colors, CSS edge pulses, fault flash.
5. Approval and veto overlays: tweetnacl keygen on first visit, IndexedDB storage, POST /keys registration, signing flow, radial countdown, blocking drawer, state-from-server on refresh.
6. Flight recorder: timeline scrubber, as-of-t pure derivation from the event array, agent run rail with cost, chain badge via verify-chain, Grafana links.
7. Chaos panel, cmdk palette, empty/loading/reconnect states.

## Gotchas

- Replay derivation must be a pure function of events[0..t]; no incremental mutation, or scrubbing backward breaks.
- The store is the only WS consumer. Components select; nothing else opens sockets or polls (metrics page 30s poll is the sole exception).
- Countdown renders from the closes_at in the event, never from a client timer started at receipt.
- Run the design-system anti-pattern checklist per screen and note each pass in the phase report.
- Test WS reconnect by restarting core-api mid-demo; the UI must recover without refresh.

## Exit ritual

Acceptance from plan/06 phase 4 (full UI-driven demo on fixtures, keyboard pass, reduced-motion pass, Lighthouse >= 90), PHASE_4_REPORT.md with screenshots, branch/tag phase-4, push, stop.
