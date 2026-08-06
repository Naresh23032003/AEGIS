"use client";

import { useEffect, useState } from "react";

const RADIUS = 16;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** plan/05-frontend.md, Gotchas: "Countdown renders from the closes_at in
 * the event, never from a client timer started at receipt." `closesAt` is
 * the only source of truth; this component just re-renders every 250ms to
 * recompute the remaining fraction against it, it never owns a duration. */
export function RadialCountdown({
  closesAt,
  totalSeconds,
}: {
  closesAt: string;
  totalSeconds: number;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, []);

  const remainingMs = Math.max(0, new Date(closesAt).getTime() - now);
  const remainingSeconds = Math.ceil(remainingMs / 1000);
  const fraction = Math.max(0, Math.min(1, remainingMs / (totalSeconds * 1000)));
  const offset = CIRCUMFERENCE * (1 - fraction);
  const color = fraction > 0.33 ? "var(--aegis-warn)" : "var(--aegis-critical)";

  return (
    <svg
      width={40}
      height={40}
      viewBox="0 0 40 40"
      role="img"
      aria-label={`${remainingSeconds} seconds remaining`}
    >
      <circle cx={20} cy={20} r={RADIUS} fill="none" stroke="var(--aegis-border)" strokeWidth={3} />
      <circle
        cx={20}
        cy={20}
        r={RADIUS}
        fill="none"
        stroke={color}
        strokeWidth={3}
        strokeLinecap="round"
        strokeDasharray={CIRCUMFERENCE}
        strokeDashoffset={offset}
        transform="rotate(-90 20 20)"
        style={{ transition: "stroke-dashoffset 0.2s linear" }}
      />
      <text
        x={20}
        y={24}
        textAnchor="middle"
        className="font-mono-data"
        fontSize={11}
        fill="var(--aegis-text)"
      >
        {remainingSeconds}
      </text>
    </svg>
  );
}
