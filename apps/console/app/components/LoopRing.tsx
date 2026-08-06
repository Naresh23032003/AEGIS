// The Observe -> Plan -> Act -> Verify indicator on every active incident
// card. plan/05-frontend.md, Ops Console: "Loop ring ... This is the
// signature visual; build it as a standalone SVG component with tests for
// each state." Pure presentational component: it takes the phases already
// derived by lib/fold.ts, it does not read the store itself.

"use client";

import { useReducedMotion } from "../hooks/useReducedMotion";
import type { LoopPhase } from "../lib/fold";

const PHASES: { key: LoopPhase; label: string }[] = [
  { key: "observe", label: "Observe" },
  { key: "plan", label: "Plan" },
  { key: "act", label: "Act" },
  { key: "verify", label: "Verify" },
];

const RADIUS = 18;
const STROKE = 4;
const GAP_DEGREES = 6;
const SEGMENT_DEGREES = 90 - GAP_DEGREES;

function arcPath(startDeg: number, endDeg: number, radius: number): string {
  const toRad = (deg: number) => ((deg - 90) * Math.PI) / 180;
  const start = { x: radius * Math.cos(toRad(startDeg)), y: radius * Math.sin(toRad(startDeg)) };
  const end = { x: radius * Math.cos(toRad(endDeg)), y: radius * Math.sin(toRad(endDeg)) };
  const largeArc = endDeg - startDeg <= 180 ? 0 : 1;
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArc} 1 ${end.x} ${end.y}`;
}

export interface LoopRingProps {
  litPhases: ReadonlySet<LoopPhase> | LoopPhase[];
  currentPhase: LoopPhase | null;
  status?: string;
  size?: number;
}

export function LoopRing({ litPhases, currentPhase, status, size = 44 }: LoopRingProps) {
  const reducedMotion = useReducedMotion();
  const lit = litPhases instanceof Set ? litPhases : new Set(litPhases);
  const isTerminal = status === "resolved" || status === "escalated";
  const summary = PHASES.map((p) => `${p.label} ${lit.has(p.key) ? "complete" : "pending"}`).join(
    ", ",
  );

  return (
    <svg
      width={size}
      height={size}
      viewBox="-22 -22 44 44"
      role="img"
      aria-label={`Loop ring: ${summary}${currentPhase ? `, currently ${currentPhase}` : ""}`}
      data-testid="loop-ring"
    >
      {PHASES.map((phase, i) => {
        const start = i * 90 + GAP_DEGREES / 2;
        const end = start + SEGMENT_DEGREES;
        const isLit = lit.has(phase.key) || isTerminal;
        const isCurrent = currentPhase === phase.key && !isTerminal;
        const color = isTerminal
          ? status === "resolved"
            ? "var(--aegis-success)"
            : "var(--aegis-critical)"
          : isLit
            ? "var(--aegis-accent)"
            : "var(--aegis-border)";
        return (
          <path
            key={phase.key}
            data-testid={`loop-ring-segment-${phase.key}`}
            data-lit={isLit}
            data-current={isCurrent}
            d={arcPath(start, end, RADIUS)}
            fill="none"
            stroke={color}
            strokeWidth={STROKE}
            strokeLinecap="round"
            opacity={isCurrent && !reducedMotion ? undefined : 1}
            className={isCurrent && !reducedMotion ? "aegis-loop-ring-pulse" : undefined}
          />
        );
      })}
      <style>{`
        @keyframes aegis-loop-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.35; }
        }
        .aegis-loop-ring-pulse {
          animation: aegis-loop-pulse 1.4s ease-in-out infinite;
        }
      `}</style>
    </svg>
  );
}
