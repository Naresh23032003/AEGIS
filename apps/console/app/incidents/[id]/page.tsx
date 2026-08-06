"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { ActionCard } from "../../components/ActionCard";
import { AgentRunRail } from "../../components/AgentRunRail";
import { ChainBadge } from "../../components/ChainBadge";
import { LoopRing } from "../../components/LoopRing";
import { Scrubber } from "../../components/Scrubber";
import { getIncidentEvents } from "../../lib/api";
import { foldIncidentEvents } from "../../lib/fold";
import { useEventStore } from "../../store/events";

export default function FlightRecorderPage() {
  const params = useParams<{ id: string }>();
  const incidentId = params.id;

  const [error, setError] = useState(false);
  const enterReplay = useEventStore((s) => s.enterReplay);
  const exitReplay = useEventStore((s) => s.exitReplay);
  const replayEvents = useEventStore((s) => s.replayEvents);
  const replayIndex = useEventStore((s) => s.replayIndex);
  const setReplayIndex = useEventStore((s) => s.setReplayIndex);

  useEffect(() => {
    let cancelled = false;
    getIncidentEvents(incidentId)
      .then((events) => {
        if (!cancelled) enterReplay(events);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
      exitReplay();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incidentId]);

  // Pure as-of-t derivation: events[0..replayIndex] only. plan/phases/
  // phase-4.md, Gotchas: "no incremental mutation, or scrubbing backward
  // breaks." No server round-trip happens on scrub; replayEvents was
  // fetched once above.
  const visibleSlice = useMemo(
    () => replayEvents.slice(0, replayIndex + 1),
    [replayEvents, replayIndex],
  );
  const view = useMemo(
    () => foldIncidentEvents(incidentId, undefined, visibleSlice),
    [incidentId, visibleSlice],
  );

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <p className="text-sm" style={{ color: "var(--aegis-critical)" }}>
          could not load incident {incidentId}
        </p>
        <Link href="/" className="text-xs" style={{ color: "var(--aegis-accent)" }}>
          back to console
        </Link>
      </div>
    );
  }

  const actions = Object.values(view.actions);

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex items-center justify-between gap-3 border-b p-3"
        style={{ borderColor: "var(--aegis-border)" }}
      >
        <div className="flex items-center gap-3">
          <Link
            href="/"
            aria-label="Back to console"
            className="rounded-md border p-1.5"
            style={{ borderColor: "var(--aegis-border)" }}
          >
            <ArrowLeft size={14} aria-hidden />
          </Link>
          <LoopRing
            litPhases={view.loopPhases}
            currentPhase={view.currentPhase}
            status={view.status}
            size={32}
          />
          <div>
            <p className="text-sm" style={{ color: "var(--aegis-text)" }}>
              {view.title || incidentId}
            </p>
            <p
              className="font-mono-data text-[10px]"
              style={{ color: "var(--aegis-text-secondary)" }}
            >
              {incidentId} · {view.status}
            </p>
          </div>
        </div>
        <ChainBadge incidentId={incidentId} />
      </div>

      <div className="border-b" style={{ borderColor: "var(--aegis-border)" }}>
        <Scrubber
          events={replayEvents}
          index={Math.max(0, replayIndex)}
          onChange={setReplayIndex}
        />
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col gap-2 overflow-y-auto p-3">
          {view.summary && (
            <p className="text-xs" style={{ color: "var(--aegis-text-secondary)" }}>
              {view.summary}
            </p>
          )}
          <p
            className="text-[10px] uppercase tracking-wide"
            style={{ color: "var(--aegis-text-secondary)" }}
          >
            actions as of this moment
          </p>
          {actions.length === 0 && (
            <p
              className="font-mono-data text-[11px]"
              style={{ color: "var(--aegis-text-secondary)" }}
            >
              no actions proposed yet
            </p>
          )}
          {actions.map((action) => (
            <ActionCard key={action.action_id} action={action} />
          ))}

          <p
            className="mt-3 text-[10px] uppercase tracking-wide"
            style={{ color: "var(--aegis-text-secondary)" }}
          >
            events up to this moment
          </p>
          <div className="flex flex-col gap-1">
            {visibleSlice.map((e) => (
              <div
                key={e.id}
                className="rounded-md border px-2 py-1 font-mono-data text-[11px]"
                style={{ borderColor: "var(--aegis-border)" }}
              >
                <span style={{ color: "var(--aegis-text-secondary)" }}>{e.ts}</span>{" "}
                <span style={{ color: "var(--aegis-accent)" }}>{e.actor}</span>{" "}
                <span style={{ color: "var(--aegis-text)" }}>{e.type}</span>
              </div>
            ))}
          </div>
        </div>
        <aside
          className="w-72 shrink-0 overflow-y-auto border-l"
          style={{ borderColor: "var(--aegis-border)" }}
        >
          <AgentRunRail runs={view.agentRuns} />
        </aside>
      </div>
    </div>
  );
}
