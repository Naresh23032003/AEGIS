// Client-side types. The wire shapes below (EventEnvelope, Incident) come
// from @aegis/contracts (generated from packages/contracts JSON Schema);
// the payload field lists per event type are transcribed from
// plan/02-contracts.md's event catalog and cross-checked against every
// `emit(..., type="...", payload={...})` call site in apps/core/aegis (see
// docs/reports/PHASE_4_REPORT.md, Deviations, for the two fields plan/02
// only sketches: agent.step's phase values and action.proposed's exact
// shape). Nothing here invents a field the backend does not send.

export type {
  EventEnvelope,
  Incident,
  ActionProposal,
  Evidence,
  VerifyResult,
} from "@aegis/contracts";

export type ActionTier = "green" | "yellow" | "red";
export type ActionStatus =
  | "proposed"
  | "denied"
  | "awaiting_approval"
  | "vetoed"
  | "executing"
  | "executed"
  | "failed"
  | "rolled_back";

export interface ActionRecord {
  id: string;
  incident_id: string;
  catalog_key: string;
  params: Record<string, unknown>;
  tier: ActionTier;
  status: string;
  confidence: number | null;
  policy_result: { allow: boolean; rule_id: string; reason: string } | null;
  reasoning: string | null;
  proposed_by: string;
  executed_at: string | null;
  result: unknown;
}

export interface AgentRunRecord {
  id: string;
  incident_id: string;
  agent: string;
  status: string;
  model: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number;
  started_at: string;
  ended_at: string | null;
}

export interface IncidentDetail {
  id: string;
  title: string;
  severity: "sev1" | "sev2" | "sev3" | null;
  status: string;
  source_rule: string;
  affected_services: string[];
  started_at: string;
  resolved_at: string | null;
  mttr_seconds: number | null;
  autonomy: "auto" | "approved" | "escalated" | null;
  summary: string | null;
  actions: ActionRecord[];
  agent_runs: AgentRunRecord[];
}

export interface CatalogEntry {
  tier: ActionTier;
  effect: string;
  rollback_key: string | null;
  params: Record<string, unknown>;
}

export interface MetricsSummary {
  mttr_avg_seconds: number | null;
  active_incidents: number;
  cost_today_usd: number;
  autonomy: { auto: number; approved: number; escalated: number };
  escalation_rate: number;
  mttr_trend: {
    incident_id: string;
    source_rule: string;
    resolved_at: string;
    mttr_seconds: number;
  }[];
  cost_per_incident: { incident_id: string; source_rule: string; cost_usd: number }[];
  loop_iterations: { incident_id: string; loops: number }[];
}
