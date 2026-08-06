"use client";

import { AnimatePresence } from "framer-motion";
import { Inbox } from "lucide-react";

import type { IncidentView } from "../lib/fold";
import { IncidentCard } from "./IncidentCard";

export interface IncidentFeedProps {
  incidents: IncidentView[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
}

export function IncidentFeed({ incidents, selectedId, onSelect, loading }: IncidentFeedProps) {
  if (loading) {
    return (
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-3" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-20 animate-pulse rounded-md border"
            style={{
              borderColor: "var(--aegis-border)",
              background: "var(--aegis-surface-raised)",
            }}
          />
        ))}
      </div>
    );
  }

  if (incidents.length === 0) {
    return (
      <div
        className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center"
        style={{ color: "var(--aegis-text-secondary)" }}
      >
        <Inbox size={22} aria-hidden />
        <p className="text-xs">No incidents yet.</p>
        <p className="font-mono-data text-[11px]">
          Inject a fault from /chaos to see AEGIS respond.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-3" aria-label="Incident feed">
      <AnimatePresence initial={false}>
        {incidents.map((incident) => (
          <IncidentCard
            key={incident.id}
            incident={incident}
            selected={incident.id === selectedId}
            onSelect={() => onSelect(incident.id)}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
