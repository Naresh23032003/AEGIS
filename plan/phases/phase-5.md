# Phase 5 brief: 3D scene, metrics, polish

Goal: the R3F topology replaces React Flow as the default renderer, the metrics page lands, and every interaction gets a polish pass.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. plan/06-milestones.md, "Phase 5" section
4. plan/05-frontend.md, "Topology scene (R3F)" section and the metrics screen paragraph
5. design-system/MASTER.md (now exists in the repo)

## Build order

1. R3F scene consuming the same `useTopologyState()` hook from phase 4: instanced node meshes on the grid, drei Html labels, edge pulse animation, emissive status colors, agent orbs with lerp choreography (max 4), single gentle camera move on fault.
2. Bloom postprocessing, DPR cap 1.5, `frameloop="demand"` when idle, invalidate on store events, full pause on hidden tab.
3. Fallback wiring: WebGL failure, `?view=2d`, and prefers-reduced-motion all route to the React Flow renderer automatically, no error flash. cmdk gets a 2D/3D toggle.
4. Metrics page (Recharts): MTTR trend per scenario, autonomy split, cost per incident, loop histogram.
5. Polish pass: walk every transition against MASTER.md; fix timing, easing, focus states, contrast.

## Gotchas

- The 3D scene renders topology state; it never subscribes to raw events. If the hook lacks something, extend the hook, both renderers benefit.
- Instanced meshes plus per-node emissive color needs per-instance color attributes; do not create one material per node.
- Measure fps with the r3f-perf overlay during an active incident and paste the numbers into the report (acceptance requires them).
- Orb choreography is cosmetic: derive positions from agent phase, do not simulate.

## Exit ritual

Acceptance from plan/06 phase 5, PHASE_5_REPORT.md with fps numbers and fallback proof (screenshot of 2D auto-load with WebGL disabled), branch/tag phase-5, push, stop.
