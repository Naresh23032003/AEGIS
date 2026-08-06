// Which of the five scenarios are currently injected, derived purely from
// the chaos.injected/chaos.cleared events on the synthetic "chaos" chain
// (apps/core/aegis/api.py, CHAOS_CHAIN_ID). plan/02-contracts.md's HTTP
// API has no GET for "what is currently injected", so this is the
// console's only source for the chaos panel's "active faults" list.

import type { EventEnvelope } from "./types";

export function activeScenarios(events: EventEnvelope[]): Set<string> {
  const active = new Set<string>();
  for (const e of events) {
    if (e.incident_id !== "chaos") continue;
    const scenario = (e.payload as { scenario?: string }).scenario;
    if (!scenario) continue;
    if (e.type === "chaos.injected") active.add(scenario);
    if (e.type === "chaos.cleared") active.delete(scenario);
  }
  return active;
}
