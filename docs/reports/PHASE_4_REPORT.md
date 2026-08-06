# Phase 4 report: Console, 2D complete

## Built

- **`design-system/MASTER.md`**: the locked tokens, motion spec, and a
  9-item anti-pattern checklist transcribed from plan/05-frontend.md.
  `npx ui-ux-pro-max-cli init --ai claude` (the tool plan/05 names) was
  blocked by this session's command sandbox; the tokens are hand-copied
  instead, byte for byte, so the source of truth is unchanged either way.
  Noted in the file itself.
- **Data layer** (`app/lib`, `app/store`, `app/hooks`):
  - `lib/ws.ts`: `EventSocket`, a reconnecting WebSocket client with
    exponential backoff (500ms to 15s, jittered), one instance for the
    whole app.
  - `store/events.ts`: the one Zustand store. `connect`/`disconnect` own
    the socket; `enterReplay`/`exitReplay`/`setReplayIndex` swap the
    store's source between the live tail and a fetched event array.
    `useVisibleEvents()` is the single read path every component uses,
    so a component genuinely cannot tell which mode it's in.
  - `lib/fold.ts`: `foldIncidentEvents`/`foldAllIncidents`, a pure
    `IncidentView` reducer over `EventEnvelope[]`. Used identically by
    the live store (folded over the running tail) and the flight
    recorder (folded over `events[0..t]`), so the two can't drift. 10 unit
    tests cover the full graph (triage through resolve), the
    veto-vs-rejected distinction, quarantine/escalation, and purity
    (same input twice, same output, input array untouched).
  - `hooks/useTopologyState.ts`: renders the five fixed nodes from
    plan/01's runtime topology table and the real call graph as edges,
    shared by this phase's React Flow fallback and reserved for phase
    5's R3F scene per plan/05's "one hook, they can never drift."
  - `lib/keys.ts`, `lib/canonicalJson.ts`, `lib/hex.ts`: tweetnacl keygen
    on first visit stored in IndexedDB (idb-keyval), `POST /keys`
    registration, and a `canonicalJson` that mirrors
    `aegis.chain.canonical_json` byte for byte (sorted keys, no
    whitespace, non-ASCII left literal). 4 unit tests pin the exact
    output against the Python implementation's documented behavior.
- **Ops Console** (`app/page.tsx`): three-column layout, live incident
  feed with spring entry (`IncidentCard`, `IncidentFeed`), the loop ring
  (`LoopRing`, a standalone SVG component, 9 unit tests, one per state:
  unlit, lit-and-current, Set vs array input, resolved-all-green,
  escalated-all-critical, pulse-only-on-current, reduced-motion
  suppression, aria-label summary), a detail panel streaming
  `agent.step` as terminal-style cards plus action cards
  (`DetailPanel`, `ActionCard`), and a metrics strip
  (`MetricsStrip`, `CountUp`) fed by `GET /metrics/summary`. The console
  auto-follows the newest incident until a user manually pins one; see
  Deviations.
- **`GET /api/metrics/summary`** (`apps/core/aegis/api.py`): the route
  plan/02-contracts.md lists but phase 2/3 never built (nothing read it
  yet). Returns `mttr_avg_seconds`, `active_incidents`, `cost_today_usd`,
  `autonomy` counts, `escalation_rate`, and three series
  (`mttr_trend`, `cost_per_incident`, `loop_iterations`) computed from
  `incidents`, `agent_runs`, and a count of `verify.passed`/`verify.failed`
  rows per incident. `source_rule` stands in for "scenario" (no scenario
  column exists and several scenarios share a detection rule, see
  Deviations).
- **Topology (React Flow)** (`Topology2D.tsx`): fixed grid layout of the
  five nodes, status-colored borders and glow (cyan healthy, red faulted,
  green verified), a custom `PulseEdge` with an `animateMotion` dot that
  speeds up and turns red when the edge's endpoint is faulted, and a
  fault-flash scale animation on the node that just turned faulted.
- **Approval and veto overlays** (`VetoCard`, `ApprovalDrawer`,
  `ApprovalOverlays`, `RadialCountdown`): mounted once in the root
  layout so a pending decision surfaces from any screen. Sign with the
  IndexedDB-stored keypair, `POST /veto` or `POST /approvals`, show the
  first 8 characters of the pubkey as a fingerprint after the decision.
  The countdown reads `closes_at` from the event and a live clock tick,
  never a client-started timer.
- **Flight recorder** (`app/incidents/[id]/page.tsx`, `Scrubber.tsx`,
  `AgentRunRail.tsx`, `ChainBadge.tsx`): fetches
  `GET /incidents/{id}/events` once, routes it into the store's replay
  mode, and scrubs by moving `replayIndex`, an as-of-t pure fold with no
  server round-trip while dragging. Chain badge calls `verify-chain`;
  agent run rail shows model, tokens, cost, and links to Grafana.
- **Chaos panel** (`app/chaos/page.tsx`, `scenarios.ts`): five scenario
  cards transcribed from plan/03's table, one inject button each, active
  faults derived purely from `chaos.injected`/`chaos.cleared` events
  (`lib/chaosState.ts`, 4 unit tests) since no HTTP route reports current
  chaos state, and a manual clear per active fault.
- **Command palette** (`CommandPalette.tsx`, cmdk): jump to incident,
  inject a scenario, toggle `?view=2d`/`?view=3d` (3D itself arrives
  phase 5), open Grafana. Global `Ctrl/Cmd+K` and a visible button.
- **Metrics page** (`app/metrics/page.tsx`): MTTR trend, autonomy split,
  cost per incident, loop-iteration histogram, all Recharts. The one
  deliberate 30s poller, per plan/05's "no polling anywhere except the
  metrics page."
- **`DesktopOnlyGate.tsx`**: below 768px, a static "best on desktop"
  notice replaces the app instead of a broken three-column layout,
  per plan/05's hard rule.
- **27 unit tests total** (`vitest` + Testing Library, new this phase:
  `npm run test -w @aegis/console`, wired into `make test-ts`): `LoopRing`
  (9, one per rendered state), `fold.ts` (10, including the full-graph
  walk and the veto-vs-rejected distinction), `canonicalJson.ts` (4),
  `chaosState.ts` (4).

## Deviations and choices

- **`ui-ux-pro-max-cli` was not run.** The npx call was denied by this
  session's command sandbox (unknown package execution). `design-system/
MASTER.md` is hand-transcribed from plan/05's locked tokens instead;
  identical content, different provenance.
- **`GET /api/metrics/summary`'s response shape is not pinned by
  plan/02** beyond "MTTR trend, autonomy rate, escalation rate, cost per
  incident, per scenario." Built the simplest shape that serves both the
  console's metrics strip and the metrics page's four charts, documented
  in `apps/core/aegis/api.py`'s docstring.
- **The loop ring's Observe/Plan/Act/Verify segments are a client-side
  display heuristic, not driven by `agent.step.phase`.** That field is
  hardcoded to `"act"` for every tool call in the current implementation
  (`apps/core/aegis/agents/nodes/_common.py`), so the ring instead lights
  segments from agent identity (triage/diagnose → observe,
  plan_remediation → plan, verify → verify) and action-lifecycle event
  types (`action.proposed`/`policy_checked` → act). No backend field was
  invented or changed; this is purely how `lib/fold.ts` interprets
  already-emitted events, documented at the top of that file.
- **Chaos panel's "active faults" list can lag real state.** It is
  derived only from `chaos.injected`/`chaos.cleared` events
  (`lib/chaosState.ts`); no event or route exists for "did the agent's
  own remediation already undo this." A scenario stays "active" (its
  inject button disabled) until someone calls the clear endpoint, even
  if e.g. `restart_service` already brought the crashed container back.
  This matches the plan's explicit "manual clear" design for the panel;
  flagged here because it surprised the first live test run of this
  phase (see Live verification).
- **Chaos panel navigates to `/`, not `/?focus=<id>`.** `POST /chaos/
{scenario}` returns the `chaos.injected` envelope, whose `incident_id`
  is the synthetic `"chaos"` chain (`apps/core/aegis/api.py`,
  `CHAOS_CHAIN_ID`), not a real incident: detection hasn't opened one yet
  at inject time. `OpsConsole` instead auto-follows the newest incident
  until a user manually clicks a different one, and stops following once
  that manual pick reaches `resolved`/`escalated` (`app/page.tsx`).
  Simpler than plumbing a not-yet-existing id through a redirect, and
  verified live to track a fresh injection correctly.
- **`ApprovalDrawer` shows the command diff and reasoning, not "evidence
  refs."** plan/05 asks for both; `action.approval_requested`'s payload
  (`{action_id, diff, reasoning}`) is all core-api actually emits, per
  plan/02's event catalog. The diagnose node's evidence list lives only
  in LangGraph state, never an event. Not fabricated.
- **Topology edge traffic level is fixed at `"medium"`.** plan/05 wants
  pulse rate to scale with a live low/med/high request-rate bucket per
  service; no route in plan/02's HTTP API exposes that to the console,
  and adding one is out of this phase's scope.
- **Two bugs found live, both fixed this phase, not carried into the
  report as known issues:**
  - `useVisibleEvents()` used to slice `replayEvents` inside the Zustand
    selector itself. That returns a new array reference on every call,
    which breaks `useSyncExternalStore`'s snapshot-caching contract and
    free-spins into React error #185 ("too many re-renders"). Reproduced
    by navigating to the flight recorder page (the first screen to flip
    the store into replay mode); fixed by selecting the four raw fields
    and computing the slice in a `useMemo` instead (`store/events.ts`).
  - React Flow's `fitView` only runs once on mount. Opening the detail
    panel resizes the topology container, and without a refit
    `target-payments` drifted off-screen behind the panel. Fixed with a
    `ResizeObserver` on the container calling `fitView()` again
    (`Topology2D.tsx`).
  - Both found by the same live playwright pass documented below, not by
    static review.
- **NavBar collapses to logo + connection badge below 640px** (Tailwind
  `sm:`), the one layout change needed to keep `DesktopOnlyGate`'s own
  chrome from causing horizontal scroll on a narrow viewport. Everything
  below the header is the static notice at that width; no other screen
  was rebuilt for phones, per plan/05's "do not attempt full mobile."
- **Cost per incident is $0.0000 across the board.** `MOCK_LLM=1`'s
  fixture player reports zero token cost (consistent with phase 3's
  Mock mode note); the chart renders correctly, the number is just flat
  by construction of the fixtures, not a bug in this phase's chart code.

## Live verification

All of this ran against a real `docker compose up` stack (`MOCK_LLM=1`),
driven by Playwright (headless Chromium) clicking the actual UI, not a
mocked one. Screenshots referenced below are in
`docs/reports/phase-4-screenshots/`.

### Full UI-driven demo, green tier

```
inject latency via UI click -> fresh incident inc_01KZB7RMJF78HES5AFG8F9RXST
  (latency_p95 on target-orders)
console: card materializes, loop ring lights observe -> plan -> act -> verify
topology: target-gateway/target-orders flash red, edge turns red
terminal state: resolved, mttr_seconds=1, autonomy=auto
action card: remove_toxic, GREEN, confidence 80%, opa: allow_green_tier
```

Screenshots: `01-console.png`, `03-console-incident-active.png`,
`04-console-auto-healed.png`, `10-flight-recorder-green.png` (chain
verified badge, full 19-event timeline, real agent_runs with model,
tokens, cost, duration for triage/diagnose/plan_remediation/verify).

### Full UI-driven demo, yellow tier with a real veto

```
inject error_spike via UI click -> fresh incident inc_01KZB7SQ43YAD4A54WW0MTY6W5
  (error_rate on target-payments)
veto card slides in bottom-right, 30s radial countdown, rollback_config,
  confidence 87%, agent reasoning shown
click "veto" -> tweetnacl signs canonical_json({action_id,decision:"veto",ts})
  with the IndexedDB keypair -> POST /api/veto/{action_id} -> 200
terminal state: escalated (not resolved) -- vetoing during the window
  escalates instead of healing, exactly as designed
```

Screenshots: `05-veto-card-open.png`, `06-veto-signed.png`,
`07-console-escalated.png`, `08-flight-recorder-full.png`,
`09-flight-recorder-scrubbed.png` (scrubber dragged to event 12 of 19,
action list and event log both correctly show only what had happened by
that point, no later events leak through).

### WebSocket reconnect, no page refresh

```
$ docker compose -f deploy/docker-compose.yml restart core-api
status badge: live -> reconnecting -> live
recovered without refresh: true (14 seconds)
```

Screenshot: `15-ws-reconnected.png`.

### Reduced motion

```
topology nodes rendered: 5 (fitView fix confirmed under the resize the
  detail panel causes)
pulsing loop-ring segments under prefers-reduced-motion: reduce: 0
animateMotion edge elements under prefers-reduced-motion: reduce: 0
```

Screenshot: `12-console-reduced-motion.png`.

### Keyboard-only pass

```
Tab, Tab from a fresh load -> focus lands on the console nav link
Ctrl+K -> command palette opens, focus lands in cmdk's own input
Escape -> palette closes
```

Screenshots: `13-command-palette-keyboard.png`,
`14-command-palette-closed.png`.

### Responsive, 1440 / 1024 / 768 / 375

```
1440px: no horizontal scroll
1024px: no horizontal scroll
 768px: no horizontal scroll
 375px: no horizontal scroll (DesktopOnlyGate notice, NavBar collapsed)
```

Screenshots: `16-responsive-1440.png` through `16-responsive-375.png`.

### Lighthouse accessibility, all four routes

```
GET / (Ops Console):              100
GET /chaos:                       100
GET /metrics:                     100
GET /incidents/{id} (flight rec): 100
```

All at or above the phase's >= 90 bar; zero failing accessibility audits
on any route.

### Anti-pattern checklist, per screen (design-system/MASTER.md)

| Screen          | 1 no gradients | 2 Lucide only | 3 cursor/focus | 4 contrast                   | 5 reduced motion   | 6 responsive | 7 timing | 8 store-only WS                             | 9 closes_at countdown                    |
| --------------- | -------------- | ------------- | -------------- | ---------------------------- | ------------------ | ------------ | -------- | ------------------------------------------- | ---------------------------------------- |
| Ops Console     | pass           | pass          | pass           | pass (contrast ratios below) | pass               | pass         | pass     | pass                                        | n/a                                      |
| Chaos Panel     | pass           | pass          | pass           | pass                         | pass               | pass         | pass     | pass                                        | n/a                                      |
| Flight Recorder | pass           | pass          | pass           | pass                         | pass               | pass         | pass     | pass                                        | n/a                                      |
| Metrics         | pass           | pass          | pass           | pass                         | n/a (no animation) | pass         | pass     | pass (30s poll is the documented exception) | n/a                                      |
| Veto card       | pass           | pass          | pass           | pass                         | pass               | pass         | pass     | pass                                        | pass (RadialCountdown reads `closes_at`) |
| Approval drawer | pass           | pass          | pass           | pass                         | pass               | pass         | pass     | pass                                        | n/a                                      |
| Command palette | pass           | pass          | pass           | pass                         | pass               | pass         | pass     | pass                                        | n/a                                      |

Contrast ratios computed against the token pairs actually used (WCAG
relative luminance): accent 10.05-11.22:1, warn 8.46-9.44:1, critical
4.95-5.52:1, success 9.45-10.55:1, text-secondary 6.17-6.89:1, all
against bg/surface/surface-raised. Worst case (critical on
surface-raised) still clears 4.5:1.

### `docker compose ps`, all 14 containers healthy

```
aegis-aegis-db-1        Up (healthy)   aegis-console-1  Up (healthy)
aegis-core-api-1        Up (healthy)   aegis-core-executor-1  Up (healthy)
aegis-core-worker-1     Up             aegis-lgtm-1  Up (healthy)
aegis-loadgen-1         Up             aegis-opa-1  Up (healthy)
aegis-toxiproxy-1       Up (healthy)   redis  Up (healthy)
shop-db                 Up (healthy)   target-gateway  Up (healthy)
target-orders           Up (healthy)   target-payments  Up (healthy)
```

`GET /api/metrics/summary` on this same live stack, real numbers from
real injected-and-healed/escalated incidents accumulated during this
phase's testing:

```
mttr_avg_seconds: 14.79
active_incidents: 0
cost_today_usd: 0.0
autonomy: {auto: 48, approved: 0, escalated: 67}
escalation_rate: 0.58
```

The escalation rate is high because most of this session's live runs
deliberately exercised the veto path (which escalates by design) and
because loadgen's own traffic trips `error_rate`/`latency_p95` on its
own periodically, same as noted in the phase 3 report; not evidence of
anything broken.

## Verification output

`make lint`:

```
.venv/bin/ruff check .
All checks passed!
.venv/bin/mypy
Success: no issues found in 50 source files
npm run lint
> eslint . (console, contracts)
npm run format:check
Checking formatting...
All matched files use Prettier code style!
```

`make test`:

```
.venv/bin/python -m pytest apps/core -q
............................................                             [100%]
44 passed, 2 warnings in 0.52s
npx -w @aegis/console tsc --noEmit
npx -w @aegis/contracts tsc --noEmit
npm run test -w @aegis/console
 Test Files  4 passed (4)
      Tests  27 passed (27)
.bin/opa test packages/policies -v
PASS: 9/9
```

`make test-python`/`opa-test` are unaffected by this phase (no agent,
policy, or executor code changed; the only backend change is the
additive `GET /metrics/summary` route). Full `make e2e` (the five chaos
scenarios against fixtures) was not rerun this phase since nothing it
covers changed; the phase's own live verification above exercises the
same green and yellow paths end to end through the real UI instead,
including one path (signed veto) `make e2e`'s fixture suite already
covers from the API side (phase 3's `test_veto_during_the_window_
escalates_instead_of_healing`).

## Not built this phase

- The R3F 3D topology scene (phase 5, per plan/06 milestones).
- The evidence pack export (phase 6).
- A live per-service traffic-rate bucket for edge pulse speed (no
  backing route yet, see Deviations).
