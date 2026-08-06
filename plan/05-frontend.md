# 05. Frontend and design system

Before any frontend work, install the design skill into the repo so it is active for every session: `npx ui-ux-pro-max-cli init --ai claude`. Then persist the design system below to design-system/MASTER.md and create page override files as screens are built.

## Design system (locked)

Style: HUD / sci-fi FUI accents on a Dark Mode OLED base. Glass surfaces only on overlays (drawers, modals, command palette). Real-Time Monitoring dashboard patterns for data areas.

| Token | Value |
|---|---|
| bg | #050607 |
| surface | #0B0E11 |
| surface-raised | #12161B |
| border | #1E242C |
| text-primary | #E6EDF3 |
| text-secondary | #8B98A5 |
| accent (healthy/agents) | #22D3EE cyan |
| warn (yellow tier, degraded) | #F59E0B amber |
| critical (faults, red tier) | #F43F5E |
| success (verified, resolved) | #34D399 |

Typography: Geist Sans for UI, Geist Mono for all data (ids, logs, metrics, hashes, countdowns). No serif anywhere.

Hard rules (from the ui-ux-pro-max anti-pattern checklist, enforce in review):

- No purple/pink AI gradients anywhere.
- Icons are Lucide SVGs only, never emojis.
- cursor-pointer on all clickable elements; visible focus rings for keyboard nav.
- Text contrast 4.5:1 minimum; test amber and cyan on the OLED background.
- prefers-reduced-motion disables all nonessential animation including the 3D scene idle motion.
- Responsive at 1440, 1024, 768; below 768 show a "best on desktop" simplified read-only view, do not attempt full mobile.
- Transitions 200-300ms; springs for card entry (motion defaults, stiffness ~260, damping ~24).

## Screens

### 1. Ops Console `/` (the money screen)

Three-column layout. Left (320px): live incident feed; incidents materialize with a spring, severity-colored left edge, each card carries the loop ring (see below). Center: topology scene (3D, next section). Right (400px, collapsible): detail panel for the selected incident streaming agent.step events as terminal-style cards. Bottom strip: global MTTR ticker, autonomy rate, active incident count, cost today, all from GET /metrics/summary, animating on change with a count-up.

Loop ring: a circular Observe -> Plan -> Act -> Verify indicator on every active incident, segments lighting as the matching agent phases stream in. This is the signature visual; build it as a standalone SVG component with tests for each state.

### 2. Flight recorder `/incidents/[id]`

Horizontal timeline scrubber across the top with every event as a tick, colored by category. Dragging the scrubber replays state: the event list, agent cards, and action states all render as-of the scrubbed moment (pure function of events up to t; replay uses GET /incidents/{id}/events, no server round-trips while scrubbing). Right rail: agent runs with model, tokens, cost; hash chain verified badge (calls verify-chain); links into Grafana for raw traces. Approve/reject cards render exactly as they appeared live, with signature fingerprints.

### 3. Chaos panel `/chaos`

Five scenario cards, each: name, what it breaks, expected agent response, one large inject button. Injecting fires POST /chaos and navigates to the console with the new incident focused. Active faults listed with a manual clear. A short "safety" footnote states injections only touch the target stack. Style this screen like a weapons console: it is the demo trigger and screenshots will circulate.

### 4. Approvals (overlay, not a route)

Yellow tier: a veto card slides in bottom-right with a 30s radial countdown, the action, the agent's reasoning, and a Veto button. Red tier: a blocking approval drawer from the right with reasoning, evidence refs, the exact command diff, and Approve / Reject. Both show the signing fingerprint (first 8 chars of pubkey) after action. Approval state must survive refresh (server is the source of truth).

### 5. Metrics `/metrics`

MTTR trend (line, per scenario), autonomy split (auto / approved / escalated), cost per incident, loop iterations histogram. Recharts, no 3D here.

Command palette (cmdk, global): jump to incident, inject scenario, toggle 2D/3D, open Grafana.

## Topology scene (R3F)

The center of the ops console. Keep it deliberate and dark, not busy.

- Nodes: target services + shop-db + redis as instanced rounded-box meshes laid out on a fixed grid over a subtle line grid floor. Labels as drei Html, mono font.
- Edges: lines with a slow animated pulse traveling in the traffic direction (custom shader or drei Line with dash offset animation). Pulse rate scales with request rate bucket (low/med/high from metrics, not per-request).
- Health: node emissive color = status (cyan healthy, amber degraded, red faulted, green just-verified with a 3s hold).
- Agents: small glowing orbs (one per active agent) that lerp from an "AEGIS core" position to the faulted node while that agent runs, orbit it while working, return on completion. Max 4 orbs; this is choreography, not simulation.
- Postprocessing: bloom only, modest intensity. Cap DPR at 1.5. `frameloop="demand"` when no incident is active; invalidate on events. Pause entirely when the tab is hidden.
- Fault moment: the affected node flashes, edges to it turn red, a brief camera ease-in toward it (no wild camera moves; one gentle move per incident).

Fallback: on WebGL context failure, or `?view=2d`, or reduced motion, render the React Flow version: same layout, same colors, CSS pulse on edges. The fallback is a first-class build target in phase 4; the 3D scene in phase 5 layers on top of the same state selector. Both consume one `useTopologyState()` hook so they can never drift.

## Frontend data layer

- One WebSocket connection (reconnecting, exponential backoff) feeding a Zustand store; all components select from the store.
- Replay mode swaps the store's source from live WS to the fetched event array; components are unaware.
- Server components for initial fetches; everything live is client-side from the store.
- No polling anywhere except the metrics page (30s refresh).
