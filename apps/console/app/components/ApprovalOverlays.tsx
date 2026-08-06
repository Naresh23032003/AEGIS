"use client";

import { useMemo } from "react";

import { foldAllIncidents } from "../lib/fold";
import { useVisibleEvents } from "../store/events";
import { ApprovalDrawer } from "./ApprovalDrawer";
import { VetoCard } from "./VetoCard";

/** Mounted once at the root layout (not a route): plan/05-frontend.md,
 * Approvals (overlay, not a route). Scans every incident's actions for an
 * open veto window or a pending red-tier approval and surfaces the
 * matching overlay app-wide, so a decision can be made from any screen. */
export function ApprovalOverlays() {
  const events = useVisibleEvents();
  const incidents = useMemo(() => Object.values(foldAllIncidents({}, events)), [events]);

  const pendingVeto = incidents
    .flatMap((incident) =>
      Object.values(incident.actions)
        .filter((a) => a.status === "veto_open")
        .map((action) => ({ incidentId: incident.id, action })),
    )
    .at(0);

  const pendingApproval = incidents
    .flatMap((incident) =>
      Object.values(incident.actions)
        .filter((a) => a.status === "awaiting_approval")
        .map((action) => ({ incidentId: incident.id, action })),
    )
    .at(0);

  return (
    <>
      {pendingVeto && (
        <VetoCard
          key={pendingVeto.action.action_id}
          incidentId={pendingVeto.incidentId}
          action={pendingVeto.action}
        />
      )}
      {pendingApproval && (
        <ApprovalDrawer
          key={pendingApproval.action.action_id}
          incidentId={pendingApproval.incidentId}
          action={pendingApproval.action}
        />
      )}
    </>
  );
}
