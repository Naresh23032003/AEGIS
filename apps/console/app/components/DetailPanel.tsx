"use client";

import { useMemo } from "react";
import Link from "next/link";
import { ArrowUpRight, Terminal, TriangleAlert, X } from "lucide-react";

import type { IncidentView } from "../lib/fold";
import { useVisibleEvents } from "../store/events";
import { ActionCard } from "./ActionCard";

const TIER_ORDER = { green: 0, yellow: 1, red: 2 } as const;

export function DetailPanel({
  incident,
  onClose,
}: {
  incident: IncidentView;
  onClose: () => void;
}) {
  const events = useVisibleEvents();
  const steps = useMemo(
    () => events.filter((e) => e.incident_id === incident.id && e.type === "agent.step"),
    [events, incident.id],
  );
  const actions = useMemo(
    () =>
      Object.values(incident.actions).sort(
        (a, b) => (TIER_ORDER[a.tier ?? "green"] ?? 0) - (TIER_ORDER[b.tier ?? "green"] ?? 0),
      ),
    [incident.actions],
  );

  return (
    <div className="flex h-full flex-col" data-testid="detail-panel">
      <div
        className="flex items-center justify-between border-b p-3"
        style={{ borderColor: "var(--aegis-border)" }}
      >
        <div className="min-w-0">
          <p className="truncate text-sm" style={{ color: "var(--aegis-text)" }}>
            {incident.title || incident.id}
          </p>
          <p
            className="font-mono-data text-[10px]"
            style={{ color: "var(--aegis-text-secondary)" }}
          >
            {incident.id}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={`/incidents/${incident.id}`}
            className="flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors duration-200"
            style={{ borderColor: "var(--aegis-border)", color: "var(--aegis-text-secondary)" }}
          >
            flight recorder
            <ArrowUpRight size={11} aria-hidden />
          </Link>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close detail panel"
            className="rounded-md border p-1 transition-colors duration-200"
            style={{ borderColor: "var(--aegis-border)", color: "var(--aegis-text-secondary)" }}
          >
            <X size={13} aria-hidden />
          </button>
        </div>
      </div>

      {incident.summary && (
        <p
          className="border-b p-3 text-xs"
          style={{ borderColor: "var(--aegis-border)", color: "var(--aegis-text-secondary)" }}
        >
          {incident.summary}
        </p>
      )}

      {incident.quarantine && (
        <div
          className="mx-3 mt-3 flex items-start gap-2 rounded-md border p-2 text-[11px]"
          style={{ borderColor: "var(--aegis-warn)", color: "var(--aegis-warn)" }}
        >
          <TriangleAlert size={13} aria-hidden />
          <span>
            {incident.quarantine.agent} quarantined: {incident.quarantine.reason} (
            {incident.quarantine.recovery})
          </span>
        </div>
      )}

      {actions.length > 0 && (
        <div
          className="flex flex-col gap-2 border-b p-3"
          style={{ borderColor: "var(--aegis-border)" }}
        >
          {actions.map((action) => (
            <ActionCard key={action.action_id} action={action} />
          ))}
        </div>
      )}

      <div
        className="flex min-h-0 flex-1 flex-col overflow-y-auto p-3"
        aria-label="Agent step stream"
      >
        <div
          className="mb-2 flex items-center gap-1.5"
          style={{ color: "var(--aegis-text-secondary)" }}
        >
          <Terminal size={12} aria-hidden />
          <span className="text-[10px] uppercase tracking-wide">agent stream</span>
        </div>
        {steps.length === 0 ? (
          <p
            className="font-mono-data text-[11px]"
            style={{ color: "var(--aegis-text-secondary)" }}
          >
            no agent steps yet
          </p>
        ) : (
          <div className="flex flex-col gap-1">
            {steps.map((step) => {
              const p = step.payload as { phase: string; thought_summary: string; tool?: string };
              return (
                <div
                  key={step.id}
                  className="rounded-md border p-2 font-mono-data text-[11px]"
                  style={{ borderColor: "var(--aegis-border)", background: "var(--aegis-bg)" }}
                >
                  <span style={{ color: "var(--aegis-accent)" }}>
                    {step.actor.replace("agent:", "")}
                  </span>
                  <span style={{ color: "var(--aegis-text-secondary)" }}> {p.phase} </span>
                  <span style={{ color: "var(--aegis-text)" }}>{p.thought_summary}</span>
                  {p.tool && (
                    <span style={{ color: "var(--aegis-text-secondary)" }}> · {p.tool}()</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
