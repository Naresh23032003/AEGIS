"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";

/** Counts actual R3F-rendered frames (not raw browser paints), so the
 * number reflects frameloop="demand" throttling faithfully instead of the
 * monitor's idle refresh rate. Sampled every 500ms, windowed against
 * performance.now() rather than R3F's own `state.clock.elapsedTime`:
 * R3F's setFrameloop() (fired on every demand<->always transition, which
 * is exactly when this number matters most) stops the clock and resets
 * elapsedTime to 0, and a window boundary computed from the pre-reset
 * value goes deeply negative and doesn't recover for many real seconds --
 * found live, by watching this meter freeze at its last value across a
 * real demand->always flip while a debug readout confirmed the frameloop
 * prop itself was changing correctly.
 *
 * plan/phases/phase-5.md asks for the r3f-perf overlay specifically; that
 * package's published version hard-depends on @react-three/drei@^9, which
 * peer-requires @react-three/fiber@^8, which in turn requires
 * react@"<19" -- incompatible with this app's React 19 / fiber v9 stack
 * (confirmed live: `npm install r3f-perf` fails ERESOLVE against the
 * console's actual react@19.2.8). This meter measures the same thing
 * (frames per second during an active incident) without pulling in a
 * second, incompatible copy of drei. */
export function FpsMeter({ onSample }: { onSample: (fps: number) => void }) {
  const frames = useRef(0);
  const windowStart = useRef(performance.now());

  useFrame(() => {
    frames.current += 1;
    const elapsedMs = performance.now() - windowStart.current;
    if (elapsedMs >= 500) {
      onSample(Math.round((frames.current * 1000) / elapsedMs));
      frames.current = 0;
      windowStart.current = performance.now();
    }
  });

  return null;
}
