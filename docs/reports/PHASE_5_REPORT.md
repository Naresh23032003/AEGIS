# Phase 5 report: 3D scene, metrics, polish

## Built

- **`app/components/Topology3D.tsx`**: the R3F scene, mounted only client-side
  (see TopologyRenderer below), consuming the exact same `useTopologyState()`
  hook as `Topology2D.tsx` so the two renderers read one source of truth and
  cannot drift, per plan/05-frontend.md's "Both consume one
  `useTopologyState()` hook."
  - **Nodes**: one `instancedMesh` (`RoundedBoxGeometry` from `three-stdlib`,
    one `MeshStandardMaterial`) holding all five nodes, per-instance color
    via `setColorAt`/`instanceColor`, per the phase brief's gotcha ("do not
    create one material per node"). True per-instance _emissive_ isn't
    wired into three's `InstancedMesh` (only the base color channel is), so
    the glow is faked with an unlit, saturated `instanceColor` plus Bloom's
    luminance threshold instead of a hand-patched shader; documented at the
    top of the component.
  - **Labels**: drei `Html`, one per node (five, not instanced -- only the
    meshes needed the instancing gotcha), mono font, same Lucide
    `Server`/`Database` icons as the 2D renderer.
  - **Edges**: drei `Line` (fat lines, `three-stdlib`'s `Line2`/
    `LineMaterial`) with `dashed` plus a per-frame `material.dashOffset`
    decrement for the traveling pulse; speed keyed off `trafficLevel`
    (low/med/high, currently always "medium" per phase 4's own
    documented limit) and roughly doubled + recolored red when faulted.
  - **Health**: node color = status, exactly the phase 4 palette (cyan
    healthy, red faulted, green verified with the existing 3s hold from
    `useTopologyState`), plus a 650ms sine-eased scale "flash" on the
    instant a node turns faulted -- the same duration as `Topology2D`'s own
    `aegis-node-flash` keyframe, so the two renderers feel identical at the
    moment of fault.
  - **Agents**: up to four glowing spheres (`AgentOrb`), keyed by agent
    name so a genuinely new agent starts at the "AEGIS core" marker and
    glides out, orbiting the faulted node while active. Position is
    derived every frame from elapsed time and slot index and lerped
    toward the orbit point -- cosmetic choreography, not a simulation, per
    the phase brief's gotcha.
  - **Camera**: `FaultCamera` eases the camera toward the first faulted
    node and back to a fixed rest framing when none is faulted, one
    continuous lerp, no OrbitControls, no idle auto-rotate -- "one gentle
    move per incident, no wild camera moves." Only mounted while
    Topology3D itself is mounted, which only happens when reduced motion
    is off (see Fallback below), so it carries no separate reduced-motion
    branch.
  - **Floor**: drei `Grid`, subtle line grid, border-token colors.
- **Bloom, DPR, frameloop**: `@react-three/postprocessing`'s
  `EffectComposer`/`Bloom` (modest intensity, `mipmapBlur`); `Canvas
dpr={[1, 1.5]}`; `frameloop` is computed per render from whether any
  node is non-healthy or any agent is active --
  `"always"` while an incident animates something, `"demand"` otherwise,
  `"never"` while the tab is hidden (`visibilitychange`). `IdleTicker`
  calls `invalidate()` every 200ms while idle so the ambient traffic pulse
  (which plan/05 wants flowing at all times, incident or not) keeps
  visibly moving at ~5fps instead of a full 60fps idle render; a fresh
  `nodes`/`edges`/`agents` value from the store also flips the `frameloop`
  prop itself immediately, which is its own invalidation.
- **`app/components/FpsMeter.tsx`**: counts real R3F-rendered frames (a
  `useFrame` counter, not `requestAnimationFrame` on its own, so it
  respects `frameloop="demand"` throttling instead of just reading the
  monitor's refresh rate), windowed against `performance.now()`. Shown at
  `?perf=1` only. r3f-perf, the package the phase brief names, was not
  used -- see Deviations.
- **`app/components/TopologyRenderer.tsx`**: picks the renderer per
  plan/05's Fallback rule. Renders `Topology2D` unconditionally on the
  first paint (identical server and client output, nothing to
  hydration-mismatch on), then a client-only effect resolves the real
  decision -- `?view=` override wins outright, otherwise reduced motion or
  a failed WebGL feature-detect (`app/lib/webgl.ts`, `hasWebGL()`) routes
  to 2D, otherwise 3D. `Topology3D` itself loads via
  `next/dynamic(..., { ssr: false })`, so it never takes part in server
  rendering at all, and is wrapped in `TopologyErrorBoundary`
  (`app/components/TopologyErrorBoundary.tsx`) for the remaining case
  feature-detection can't catch: a context that reports available but
  then fails during `Canvas` construction, or is lost at runtime
  (`webglcontextlost`, handled in `Topology3D`'s `onCreated`). `app/lib/
viewParam.ts` holds the shared `?view=` reader and a
  `VIEW_CHANGED_EVENT` that `CommandPalette`'s existing 2D/3D toggle now
  dispatches after its `router.push`, so a toggle click is picked up
  immediately instead of waiting on a `popstate` that a client-side push
  never fires. `page.tsx` now renders `TopologyRenderer` instead of
  `Topology2D` directly.
- **Metrics page**: already fully built in phase 4 (`app/metrics/page.tsx`,
  MTTR trend, autonomy split, cost per incident, loop histogram, Recharts,
  Lighthouse 100 at the time) -- carried forward unchanged this phase, not
  rebuilt. plan/06's phase 5 acceptance doesn't ask for anything new here.
- **Polish pass**: walked the anti-pattern checklist from
  `design-system/MASTER.md` against the new surfaces this phase actually
  touched (the topology area and the command palette's toggle); table
  below. No changes were needed to the four screens phase 4 already
  checked (Ops Console, Chaos Panel, Flight Recorder, Metrics) since none
  of their own markup changed this phase -- only what renders inside the
  Ops Console's topology slot did.
- **6 new unit tests** (`webgl.test.ts`, `viewParam.test.ts`): `hasWebGL()`
  against jsdom's real (absent) canvas support, a mocked available
  context, and a throwing `getContext`; `readViewParam()` against a real
  URL via `history.pushState`. `make test-ts` now runs 33 tests total (27
  carried from phase 4 unchanged, 6 new).

## Deviations and choices

- **r3f-perf was not installed.** Its published version depends on
  `@react-three/drei@^9.103.0`, which peer-requires
  `@react-three/fiber@^8`, which requires `react@">=18.0 <19"` --
  incompatible with this app's `react@19.2.8` and the `@react-three/
fiber@^9`/`@react-three/drei@^10` this phase needs for React 19 support.
  Confirmed live: `npm install r3f-perf` and `npm install
@react-three/fiber@^8` both fail `ERESOLVE` against the console's actual
  dependency tree (ERESOLVE logs not reproduced here; trivially
  reproducible with either install command in `apps/console`).
  `FpsMeter.tsx` measures the same thing -- real R3F-rendered frames per
  second -- without a second, incompatible copy of drei.
- **A real bug, found live and fixed this phase**: `FpsMeter`'s first
  version windowed against `state.clock.elapsedTime`. R3F's internal
  `setFrameloop()` (which fires on every `"demand"`<->`"always"`
  transition -- exactly the moment this number matters) stops the clock
  and resets `elapsedTime` to 0. The meter's own window-start reference
  didn't reset in step, so the elapsed-time math went deeply negative
  after a transition and didn't recover for many real seconds, freezing
  the displayed fps at its pre-transition value right when an incident
  went active. Found by adding a temporary debug readout of the raw
  `frameloop` prop and `hasActiveIncident` value next to the fps number,
  confirming live that the frameloop prop _was_ flipping to `"always"`
  correctly while the displayed fps stayed flat -- isolating the bug to
  the meter's own windowing, not the render-loop wiring. Fixed by
  windowing against `performance.now()` instead (see FpsMeter.tsx's own
  comment); the debug readout was removed once the fix was confirmed live
  (screenshots/samples below are all post-fix).
- **`RoundedBoxGeometry` comes from `three-stdlib`, added as an explicit
  console dependency** (it was already present transitively through drei,
  but importing a package this component actually uses without declaring
  it directly is fragile if drei ever drops it).
- **Instanced-mesh emissive is approximated**, not literally per-instance
  emissive -- see Built, above.
- **Camera vantage on fault is a fixed offset from the faulted node's
  position**, not a framing computed from the full topology bounds; five
  fixed nodes on a fixed grid makes this the simplest thing that reads
  correctly for every node, per CLAUDE.md's "choose the simplest thing
  that passes the phase's acceptance criteria."
- **`make e2e` was not rerun.** No backend, contracts, or policy code
  changed this phase (console-only), matching phase 4's own note that a
  console-only phase doesn't touch anything the Python e2e suite covers;
  `make lint test` (below) is the full regression net for what _did_
  change, plus this phase's own live browser verification.
- **Responsive check for phase 5 was narrower than phase 4's.** Phase 4
  did a full Lighthouse + keyboard + contrast pass per screen; this phase
  re-verified only what actually changed (no horizontal overflow at
  1440/1024/768 with the 3D renderer active, screenshots below) rather
  than rerunning the full phase 4 audit against unchanged screens.

## Live verification

Against the real `docker compose up` stack (`MOCK_LLM=1`), driven by
Playwright (Chromium) against the actual built console image, not a dev
server. Screenshots in `docs/reports/phase-5-screenshots/`.

### Default renderer is 3D

```
GET /?perf=1 -> [data-testid="topology-3d"] present, [data-testid="topology-2d"] absent
```

Screenshot: `17-topology3d-idle.png`.

### Fault -> agent run -> verified, fps sampled throughout

Injected `latency` via the real `POST /api/chaos/latency`. Fps sampled
every ~300ms in lockstep with a read of each node's own
`data-status` attribute (so every sample is tagged with what the scene
itself was rendering, not assumed from a fixed delay):

```
sceneActive=true samples (24): 39, 39, 60, 60, 60, 60, 7, 7, 49, 60, 60,
  60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60
sceneActive=false samples (9):  60, 27, 27, 7, 7, 7, 7, 5, 5
```

18 of 24 active-window samples sit at 60 -- this machine's display refresh
cap, i.e. the scene is not the bottleneck. The two `7, 7` dips inside the
active window are the ~600ms ramp right after a fresh `"demand"->"always"`
flip (a second, independent incident opened right on the heels of the
first); every active window converges to a flat 60 within one ramp step
and holds there, including through the "verified" 3-second color hold.
The idle-window samples show `frameloop="demand"` doing its job: once
nothing is animating, fps drops to the ~5-7fps `IdleTicker` rate instead
of a continuous 60fps idle render.

Machine: MacBook Air, Apple M4 (`system_profiler SPHardwareDataType`).
Measured in headed Chromium, not headless -- headless Chromium renders
WebGL through SwiftShader (software) by default, which understates real
fps by roughly 5-8x on this hardware in a spot check; headed mode gets
the real ANGLE/Metal-backed GPU path a person actually sees.

Screenshots: `18-topology3d-fault.png` (camera eased in on the faulted
`target-orders`, red node + edges), `19-topology3d-agent-orbs.png`
(mid-run, agent stream visible in the detail panel; this particular frame
didn't happen to land on an active orb -- the orb window is brief and
wasn't specifically chased across retries), `20-topology3d-resolved.png`.

Full incident: `inc_01KZC451KA0XN1R42TN11QP2ET`, `latency_p95` on
`target-gateway`, resolved, `mttr_seconds: 2`, zero page errors
(`page.on("pageerror")`) across the whole run.

### `?view=2d` forces the fallback

```
GET /?view=2d -> topology-2d present, topology-3d absent
```

Screenshot: `21-view-2d-forced.png`.

### `prefers-reduced-motion: reduce` routes to 2D automatically

```
page.emulateMedia({ reducedMotion: "reduce" }); GET /
  -> topology-2d present, topology-3d absent, 0 page errors
```

Screenshot: `22-reduced-motion-2d.png`.

### WebGL disabled routes to 2D, no error flash

Separate Chromium launch with `--disable-webgl --disable-webgl2
--disable-3d-apis --disable-gpu`:

```
webglAvailableInThisBrowser (page's own hasWebGL()-equivalent check): false
GET / -> topology-2d present, topology-3d absent
0 page errors, no "application error"/"unhandled"/"something went wrong" text in body
```

Screenshot: `23-webgl-disabled-2d-fallback.png` -- a completely normal-
looking Ops Console, not a broken or blank page.

### Responsive, 1440 / 1024 / 768, 3D renderer active

```
1440px: scrollWidth 1440 == clientWidth 1440, no overflow
1024px: scrollWidth 1024 == clientWidth 1024, no overflow
 768px: scrollWidth  768 == clientWidth  768, no overflow (DesktopOnlyGate)
```

Screenshots: `24-responsive-1440.png`, `24-responsive-1024.png`,
`24-responsive-768.png`.

### Anti-pattern checklist, surfaces this phase touched

| Check                  | Topology3D                                                                                                                                                    | CommandPalette toggle |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| 1 no gradients         | pass (cyan/red/green/dark only)                                                                                                                               | pass (unchanged)      |
| 2 Lucide only          | pass (Server/Database/Bot, same as 2D)                                                                                                                        | pass (unchanged)      |
| 3 cursor/focus         | n/a -- no clickable elements in the 3D tree (matches 2D's `selectable: false`)                                                                                | pass (unchanged)      |
| 4 contrast             | pass -- labels use `--aegis-text` on real DOM (Html), same tokens as every other screen                                                                       | pass (unchanged)      |
| 5 reduced motion       | pass -- verified live, scene doesn't mount at all under reduced motion                                                                                        | n/a                   |
| 6 responsive           | pass -- verified live, no overflow at 1440/1024/768                                                                                                           | pass (unchanged)      |
| 7 timing               | pass -- fault flash matches 2D's 650ms exactly; camera/orbit are continuous easing, not a fixed-duration UI transition, by design (plan/05's own camera spec) | pass (unchanged)      |
| 8 store-only WS        | pass -- `useTopologyState()` only, `FpsMeter`/`IdleTicker` never open a socket or poll                                                                        | pass (unchanged)      |
| 9 closes\_at countdown | n/a                                                                                                                                                           | n/a                   |

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
...............................................                          [100%]
47 passed, 2 warnings in 0.69s
npx -w @aegis/console tsc --noEmit
npx -w @aegis/contracts tsc --noEmit
npm run test -w @aegis/console
 Test Files  6 passed (6)
      Tests  33 passed (33)
.bin/opa test packages/policies -v
PASS: 9/9
```

`docker compose ps`, all 14 containers healthy at verification time (same
set as phase 4's table, unchanged this phase).

## Not built this phase

- A live per-service traffic-rate bucket for edge pulse speed (still fixed
  at "medium", inherited limit from phase 4, no backing route yet).
- The evidence pack export and remaining phase 6 items.
