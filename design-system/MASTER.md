# AEGIS design system

Source: plan/05-frontend.md, "Design system (locked)". This file is the
review gate referenced in plan/phases/phase-4.md; every screen is checked
against the anti-pattern checklist below before commit, and the check is
noted in the phase report. `npx ui-ux-pro-max-cli init --ai claude` (the
tool named in plan/05) was blocked by the session's command sandbox on
this run; the tokens and rules below are hand-transcribed from plan/05
instead, byte for byte, so the source of truth is unchanged either way.

## Style

HUD / sci-fi FUI accents on a dark OLED base. Glass surfaces only on
overlays (drawers, modals, command palette): `backdrop-filter: blur(12px)`
over `surface-raised` at 80% alpha, never on a base page surface. Data
areas follow real-time monitoring dashboard conventions: dense, mono
numerals, no decorative chrome.

## Tokens

| Token                        | Value         | CSS var                  |
| ---------------------------- | ------------- | ------------------------ |
| bg                           | #050607       | `--aegis-bg`             |
| surface                      | #0B0E11       | `--aegis-surface`        |
| surface-raised               | #12161B       | `--aegis-surface-raised` |
| border                       | #1E242C       | `--aegis-border`         |
| text-primary                 | #E6EDF3       | `--aegis-text`           |
| text-secondary               | #8B98A5       | `--aegis-text-secondary` |
| accent (healthy/agents)      | #22D3EE cyan  | `--aegis-accent`         |
| warn (yellow tier, degraded) | #F59E0B amber | `--aegis-warn`           |
| critical (faults, red tier)  | #F43F5E       | `--aegis-critical`       |
| success (verified, resolved) | #34D399       | `--aegis-success`        |

Typography: Geist Sans for UI text, Geist Mono for all data (ids, logs,
metrics, hashes, countdowns). No serif anywhere. Loaded via `next/font`
in `app/layout.tsx`, exposed as `--font-sans` / `--font-mono`.

Motion: transitions 200-300ms. Card entry springs at stiffness ~260,
damping ~24 (framer-motion `{ type: "spring", stiffness: 260, damping: 24 }`).
One easing family for everything else: `cubic-bezier(0.4, 0, 0.2, 1)`.

## Anti-pattern checklist (review gate, run per screen)

1. No purple/pink AI gradients anywhere.
2. Icons are Lucide SVGs only, never emojis.
3. `cursor-pointer` on all clickable elements; visible focus rings
   (`:focus-visible`) for keyboard nav, never suppressed.
4. Text contrast 4.5:1 minimum against `--aegis-bg` / `--aegis-surface`;
   amber and cyan both checked, not assumed.
5. `prefers-reduced-motion: reduce` disables all nonessential animation,
   including the 3D scene idle motion (phase 5) and this phase's spring
   entries, count-ups, and pulse loops.
6. Responsive at 1440 / 1024 / 768. Below 768, a read-only simplified
   view with a "best on desktop" notice; no attempt at a full mobile
   layout.
7. Transitions 200-300ms; card entry uses the spring above, nothing
   snaps or instantly appears except live data ticks.
8. The store is the only WebSocket consumer; a screen that opens its own
   socket or polls (outside the metrics page's 30s poll) fails this
   check.
9. Countdown timers render from a `closes_at` timestamp in event data,
   never from a client-side timer started at receipt.

Per-screen pass results are recorded in docs/reports/PHASE_4_REPORT.md,
one line per numbered item, screen by screen.

## Layout

Screens per plan/05: Ops Console (`/`), Flight Recorder
(`/incidents/[id]`), Chaos Panel (`/chaos`), Metrics (`/metrics`).
Approval/veto surfaces are overlays, not routes. Global command palette
(cmdk) mounted once in the root layout.

Component locations:

- `app/lib/`: WS client, canonical JSON, signing, IndexedDB key store.
- `app/store/`: the one Zustand store (`useEventStore`).
- `app/hooks/`: `useTopologyState()`, shared with the phase 5 3D scene.
- `app/components/`: screen-agnostic UI (LoopRing, IncidentCard,
  Topology2D, ApprovalDrawer, VetoCard, CommandPalette, CountUp, …).
