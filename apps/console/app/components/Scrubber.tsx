"use client";

import type { EventEnvelope } from "../lib/types";

const CATEGORY_COLOR: Record<string, string> = {
  chaos: "var(--aegis-critical)",
  incident: "var(--aegis-warn)",
  agent: "var(--aegis-accent)",
  action: "var(--aegis-text)",
  verify: "var(--aegis-success)",
};

function categoryOf(type: string): string {
  return type.split(".")[0] ?? type;
}

/** plan/05-frontend.md, Flight recorder: "Horizontal timeline scrubber
 * across the top with every event as a tick, colored by category.
 * Dragging the scrubber replays state." Purely a range input over the
 * event index; the derivation itself lives in lib/fold.ts. */
export function Scrubber({
  events,
  index,
  onChange,
}: {
  events: EventEnvelope[];
  index: number;
  onChange: (index: number) => void;
}) {
  if (events.length === 0) {
    return <div className="h-14" />;
  }

  const firstEvent = events[0]!;
  const lastEvent = events[events.length - 1]!;
  const first = new Date(firstEvent.ts).getTime();
  const last = new Date(lastEvent.ts).getTime();
  const span = Math.max(1, last - first);

  return (
    <div className="flex flex-col gap-1 px-4 py-3" data-testid="scrubber">
      <div className="relative h-4">
        {events.map((e, i) => {
          const t = (new Date(e.ts).getTime() - first) / span;
          return (
            <div
              key={e.id}
              title={`${e.type} @ ${e.ts}`}
              className="absolute top-0 h-4 w-[2px]"
              style={{
                left: `${t * 100}%`,
                background: CATEGORY_COLOR[categoryOf(e.type)] ?? "var(--aegis-border)",
                opacity: i <= index ? 1 : 0.25,
              }}
            />
          );
        })}
      </div>
      <input
        type="range"
        min={0}
        max={events.length - 1}
        value={index}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label="Replay scrubber"
        className="w-full accent-[var(--aegis-accent)]"
      />
      <div
        className="flex justify-between font-mono-data text-[10px]"
        style={{ color: "var(--aegis-text-secondary)" }}
      >
        <span>{firstEvent.ts}</span>
        <span data-testid="scrubber-current-event">
          {index + 1}/{events.length} · {events[index]?.type}
        </span>
        <span>{lastEvent.ts}</span>
      </div>
    </div>
  );
}
