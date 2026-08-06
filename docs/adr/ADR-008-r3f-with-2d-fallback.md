# ADR-008: R3F topology with automatic 2D React Flow fallback

## Status

Accepted.

## Context

The 3D topology scene is the visual centerpiece of the demo, but WebGL is
not guaranteed: older hardware, some sandboxed browsers, and
`prefers-reduced-motion` users all need a version of the same information
that does not depend on it. A demo that shows a blank canvas or an error to
even a small fraction of viewers undermines the "provable trust" pitch more
than a plainer screen would.

## Decision

Build the primary topology view in React Three Fiber, backed by a shared
`useTopologyState` hook. If WebGL is unavailable, if `prefers-reduced-motion`
is set, or the URL has `?view=2d`, render the same state through
`@xyflow/react` instead.

## Consequences

Every viewer sees the incident graph regardless of hardware or preference,
with no error flash on the failure path (checked before first paint, not
caught after). The two renderers share one state hook, so they cannot drift
into showing different information, only different presentations of it.
Building and maintaining two renderers is real ongoing cost; it is paid once
here so the demo degrades gracefully instead of breaking.
