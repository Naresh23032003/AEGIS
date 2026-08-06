"use client";

import { motion } from "framer-motion";

import { useReducedMotion } from "../hooks/useReducedMotion";
import type { IncidentView } from "../lib/fold";
import { LoopRing } from "./LoopRing";

const SEVERITY_COLOR: Record<string, string> = {
  sev1: "var(--aegis-critical)",
  sev2: "var(--aegis-warn)",
  sev3: "var(--aegis-accent)",
};

const STATUS_LABEL: Record<string, string> = {
  open: "detected",
  resolving: "resolving",
  awaiting_approval: "awaiting approval",
  resolved: "resolved",
  escalated: "escalated",
};

const STATUS_COLOR: Record<string, string> = {
  open: "var(--aegis-warn)",
  resolving: "var(--aegis-accent)",
  awaiting_approval: "var(--aegis-warn)",
  resolved: "var(--aegis-success)",
  escalated: "var(--aegis-critical)",
};

const SPRING = { type: "spring" as const, stiffness: 260, damping: 24 };

export interface IncidentCardProps {
  incident: IncidentView;
  selected: boolean;
  onSelect: () => void;
}

export function IncidentCard({ incident, selected, onSelect }: IncidentCardProps) {
  const reducedMotion = useReducedMotion();
  const edgeColor = incident.severity ? SEVERITY_COLOR[incident.severity] : "var(--aegis-border)";
  const statusColor = STATUS_COLOR[incident.status] ?? "var(--aegis-text-secondary)";

  return (
    <motion.button
      type="button"
      layout={!reducedMotion}
      initial={reducedMotion ? false : { opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reducedMotion ? { duration: 0 } : SPRING}
      onClick={onSelect}
      aria-pressed={selected}
      data-testid="incident-card"
      data-incident-id={incident.id}
      className="flex w-full items-start gap-3 rounded-md border-l-4 border-y border-r p-3 text-left transition-colors duration-200"
      style={{
        borderLeftColor: edgeColor,
        borderTopColor: "var(--aegis-border)",
        borderRightColor: "var(--aegis-border)",
        borderBottomColor: "var(--aegis-border)",
        background: selected ? "var(--aegis-surface-raised)" : "var(--aegis-surface)",
      }}
    >
      <LoopRing
        litPhases={incident.loopPhases}
        currentPhase={incident.currentPhase}
        status={incident.status}
        size={36}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm" style={{ color: "var(--aegis-text)" }}>
            {incident.title || incident.id}
          </p>
        </div>
        <div
          className="mt-1 flex items-center gap-2 font-mono-data text-[10px]"
          style={{ color: "var(--aegis-text-secondary)" }}
        >
          <span style={{ color: statusColor }}>
            {STATUS_LABEL[incident.status] ?? incident.status}
          </span>
          {incident.severity && <span>{incident.severity}</span>}
          {incident.mttrSeconds != null && <span>{incident.mttrSeconds}s</span>}
          {incident.autonomy && <span>{incident.autonomy}</span>}
        </div>
        {incident.affectedServices.length > 0 && (
          <p
            className="mt-1 truncate font-mono-data text-[10px]"
            style={{ color: "var(--aegis-text-secondary)" }}
          >
            {incident.affectedServices.join(", ")}
          </p>
        )}
      </div>
    </motion.button>
  );
}
