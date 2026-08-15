// Pure fold: IncidentView = reduce(events[0..t]). Used identically by the
// live store (folded incrementally as events arrive) and by the flight
// recorder (folded over events.slice(0, scrubIndex + 1)) so the two paths
// can never drift (plan/phases/phase-4.md, Gotchas: "Replay derivation
// must be a pure function of events[0..t]; no incremental mutation").
//
// The Observe/Plan/Act/Verify loop-ring mapping below is a client-side
// display heuristic, not a new backend field: plan/03's graph node order
// is triage -> diagnose -> plan_remediation -> gate -> execute -> verify,
// and agent.step's own `phase` field is always "act" in the current
// implementation (apps/core/aegis/agents/nodes/_common.py hardcodes it
// for every tool call), so the ring segments are driven by node/agent
// identity and action-lifecycle event types instead. See
// docs/reports/PHASE_4_REPORT.md, Deviations.

import type { ActionTier, EventEnvelope } from "./types";

export type LoopPhase = "observe" | "plan" | "act" | "verify";

const AGENT_LOOP_PHASE: Record<string, LoopPhase> = {
  triage: "observe",
  diagnose: "observe",
  plan_remediation: "plan",
  verify: "verify",
};

export interface ActionView {
  action_id: string;
  catalog_key?: string;
  params?: Record<string, unknown>;
  tier?: ActionTier;
  /** The model's confidence in this action. */
  confidence?: number;
  /** The diagnose node's confidence in the cause this action addresses,
   * copied onto action.proposed at propose time (plan/02-contracts.md,
   * Event catalog). A different number from `confidence` and routinely a
   * much lower one, so the two are always labelled apart in the UI. */
  diagnosisConfidence?: number;
  reasoning?: string;
  rollback_key?: string | null;
  status:
    | "proposed"
    | "denied"
    | "veto_open"
    | "awaiting_approval"
    | "executing"
    | "executed"
    | "failed"
    | "vetoed"
    | "rejected"
    | "rolled_back";
  opaRuleId?: string;
  policyDecision?: "allow" | "deny";
  vetoClosesAt?: string;
  approvalDiff?: { catalog_key: string; params: Record<string, unknown> };
  approvalReasoning?: string;
  decidedBy?: string;
  rejectReason?: string;
  result?: unknown;
  durationMs?: number;
}

export interface AgentRunView {
  agent: string;
  model?: string;
  status: "running" | "completed" | "failed";
  tokensIn?: number;
  tokensOut?: number;
  costUsd?: number;
  durationMs?: number;
  reason?: string;
}

export interface IncidentView {
  id: string;
  title: string;
  severity: "sev1" | "sev2" | "sev3" | null;
  status: string;
  sourceRule?: string;
  affectedServices: string[];
  summary: string | null;
  mttrSeconds: number | null;
  autonomy: string | null;
  startedAt?: string;
  resolvedAt?: string | null;
  loopPhases: Set<LoopPhase>;
  currentPhase: LoopPhase | null;
  activeAgents: string[];
  agentRuns: Record<string, AgentRunView>;
  actions: Record<string, ActionView>;
  quarantine?: { agent: string; reason: string; recovery: string };
  escalation?: { reason: string; loopsExhausted: boolean };
  lastEventAt: string;
}

export function emptyIncidentView(id: string): IncidentView {
  return {
    id,
    title: "",
    severity: null,
    status: "open",
    affectedServices: [],
    summary: null,
    mttrSeconds: null,
    autonomy: null,
    loopPhases: new Set(),
    currentPhase: null,
    activeAgents: [],
    agentRuns: {},
    actions: {},
    lastEventAt: "",
  };
}

// One loose shape covering every event payload's fields (transcribed from
// the emit() call sites, see the file header comment). Each event type
// only ever sets a subset of these; the fields are typed as always
// present because this is an unchecked type assertion bridging a known
// backend contract into TypeScript, not a runtime-validated shape -- the
// switch case for each event type only ever reads the subset that type
// actually sends. plan/02-contracts.md itself specifies payloads just as
// loosely ("payload highlights").
interface AnyEventPayload {
  rule: string;
  service: string;
  severity: "sev1" | "sev2" | "sev3" | null;
  affected_services: string[];
  summary: string;
  agent: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  duration_ms: number;
  reason: string;
  recovery: string;
  action_id: string;
  catalog_key: string;
  params: Record<string, unknown>;
  tier: ActionTier;
  confidence: number;
  diagnosis_confidence: number;
  reasoning: string;
  rollback_key: string | null;
  opa_rule_id: string;
  decision: "allow" | "deny";
  closes_at: string;
  diff: { catalog_key: string; params: Record<string, unknown> };
  approver_pubkey: string;
  status: string;
  result: unknown;
  rollback_of: string;
  mttr_seconds: number;
  autonomy: string;
  loops_exhausted: boolean;
}

function applyEvent(view: IncidentView, e: EventEnvelope): IncidentView {
  const p = e.payload as unknown as AnyEventPayload;
  switch (e.type) {
    case "incident.detected": {
      const services = new Set(view.affectedServices);
      services.add(p.service);
      return {
        ...view,
        title: view.title || `${p.rule} on ${p.service}`,
        sourceRule: p.rule,
        affectedServices: Array.from(services),
        startedAt: view.startedAt ?? e.ts,
        lastEventAt: e.ts,
      };
    }
    case "incident.classified":
      return {
        ...view,
        severity: p.severity,
        affectedServices: p.affected_services,
        summary: p.summary,
        lastEventAt: e.ts,
      };
    case "agent.run.started": {
      const phase = AGENT_LOOP_PHASE[p.agent as string];
      const loopPhases = new Set(view.loopPhases);
      if (phase) loopPhases.add(phase);
      const activeAgents = view.activeAgents.includes(p.agent)
        ? view.activeAgents
        : [...view.activeAgents, p.agent];
      return {
        ...view,
        status: view.status === "open" ? "resolving" : view.status,
        loopPhases,
        currentPhase: phase ?? view.currentPhase,
        activeAgents,
        agentRuns: {
          ...view.agentRuns,
          [p.agent]: { agent: p.agent, model: p.model, status: "running" },
        },
        lastEventAt: e.ts,
      };
    }
    case "agent.run.completed":
      return {
        ...view,
        activeAgents: view.activeAgents.filter((a) => a !== p.agent),
        agentRuns: {
          ...view.agentRuns,
          [p.agent]: {
            ...(view.agentRuns[p.agent] ?? { agent: p.agent, status: "running" }),
            status: "completed",
            tokensIn: p.tokens_in,
            tokensOut: p.tokens_out,
            costUsd: p.cost_usd,
            durationMs: p.duration_ms,
          },
        },
        lastEventAt: e.ts,
      };
    case "agent.run.failed":
      return {
        ...view,
        activeAgents: view.activeAgents.filter((a) => a !== p.agent),
        agentRuns: {
          ...view.agentRuns,
          [p.agent]: {
            ...(view.agentRuns[p.agent] ?? { agent: p.agent, status: "running" }),
            status: "failed",
            reason: p.reason,
          },
        },
        lastEventAt: e.ts,
      };
    case "agent.quarantined":
      return {
        ...view,
        quarantine: { agent: p.agent, reason: p.reason, recovery: p.recovery },
        lastEventAt: e.ts,
      };
    case "action.proposed": {
      const loopPhases = new Set(view.loopPhases);
      loopPhases.add("plan");
      return {
        ...view,
        loopPhases,
        currentPhase: "plan",
        actions: {
          ...view.actions,
          [p.action_id]: {
            action_id: p.action_id,
            catalog_key: p.catalog_key,
            params: p.params,
            tier: p.tier,
            confidence: p.confidence,
            diagnosisConfidence: p.diagnosis_confidence,
            reasoning: p.reasoning,
            rollback_key: p.rollback_key,
            status: "proposed",
          },
        },
        lastEventAt: e.ts,
      };
    }
    case "action.policy_checked": {
      const existing: ActionView = view.actions[p.action_id] ?? {
        action_id: p.action_id,
        status: "proposed",
      };
      const loopPhases = new Set(view.loopPhases);
      loopPhases.add("act");
      return {
        ...view,
        loopPhases,
        currentPhase: "act",
        actions: {
          ...view.actions,
          [p.action_id]: {
            ...existing,
            opaRuleId: p.opa_rule_id,
            policyDecision: p.decision,
            status: p.decision === "deny" ? "denied" : existing.status,
          },
        },
        lastEventAt: e.ts,
      };
    }
    case "action.veto_window_opened": {
      const existing: ActionView = view.actions[p.action_id] ?? {
        action_id: p.action_id,
        status: "proposed",
      };
      return {
        ...view,
        actions: {
          ...view.actions,
          [p.action_id]: { ...existing, status: "veto_open", vetoClosesAt: p.closes_at },
        },
        lastEventAt: e.ts,
      };
    }
    case "action.approval_requested": {
      const existing: ActionView = view.actions[p.action_id] ?? {
        action_id: p.action_id,
        status: "proposed",
      };
      return {
        ...view,
        status: "awaiting_approval",
        actions: {
          ...view.actions,
          [p.action_id]: {
            ...existing,
            status: "awaiting_approval",
            approvalDiff: p.diff,
            approvalReasoning: p.reasoning,
          },
        },
        lastEventAt: e.ts,
      };
    }
    case "action.approved": {
      const existing: ActionView = view.actions[p.action_id] ?? {
        action_id: p.action_id,
        status: "proposed",
      };
      return {
        ...view,
        actions: {
          ...view.actions,
          [p.action_id]: { ...existing, status: "executing", decidedBy: p.approver_pubkey },
        },
        lastEventAt: e.ts,
      };
    }
    case "action.rejected": {
      const existing: ActionView = view.actions[p.action_id] ?? {
        action_id: p.action_id,
        status: "proposed",
      };
      const wasVeto = existing.status === "veto_open";
      return {
        ...view,
        actions: {
          ...view.actions,
          [p.action_id]: {
            ...existing,
            status: wasVeto ? "vetoed" : "rejected",
            decidedBy: p.approver_pubkey,
            rejectReason: p.reason,
          },
        },
        lastEventAt: e.ts,
      };
    }
    case "action.executed": {
      const existing: ActionView = view.actions[p.action_id] ?? {
        action_id: p.action_id,
        status: "proposed",
      };
      return {
        ...view,
        actions: {
          ...view.actions,
          [p.action_id]: {
            ...existing,
            catalog_key: existing.catalog_key ?? p.catalog_key,
            params: existing.params ?? p.params,
            status: p.status === "executed" ? "executed" : "failed",
            result: p.result,
            durationMs: p.duration_ms,
          },
        },
        lastEventAt: e.ts,
      };
    }
    case "action.rolled_back": {
      const existing: ActionView = view.actions[p.rollback_of] ?? {
        action_id: p.rollback_of,
        status: "proposed",
      };
      return {
        ...view,
        actions: { ...view.actions, [p.rollback_of]: { ...existing, status: "rolled_back" } },
        lastEventAt: e.ts,
      };
    }
    case "verify.passed": {
      const loopPhases = new Set(view.loopPhases);
      loopPhases.add("verify");
      return { ...view, loopPhases, currentPhase: "verify", lastEventAt: e.ts };
    }
    case "verify.failed": {
      const loopPhases = new Set(view.loopPhases);
      loopPhases.add("verify");
      return { ...view, loopPhases, currentPhase: "observe", lastEventAt: e.ts };
    }
    case "incident.resolved":
      return {
        ...view,
        status: "resolved",
        mttrSeconds: p.mttr_seconds,
        autonomy: p.autonomy,
        resolvedAt: e.ts,
        currentPhase: null,
        activeAgents: [],
        lastEventAt: e.ts,
      };
    case "incident.escalated":
      return {
        ...view,
        status: "escalated",
        escalation: { reason: p.reason, loopsExhausted: p.loops_exhausted },
        currentPhase: null,
        activeAgents: [],
        lastEventAt: e.ts,
      };
    default:
      return { ...view, lastEventAt: e.ts };
  }
}

/** Folds every event in `events` addressed to `incidentId` onto `seed`
 * (a REST-fetched snapshot, or undefined for a WS-only incident). Pure:
 * same inputs, same output, every time. */
export function foldIncidentEvents(
  incidentId: string,
  seed: Partial<IncidentView> | undefined,
  events: EventEnvelope[],
): IncidentView {
  let view: IncidentView = { ...emptyIncidentView(incidentId), ...seed };
  for (const e of events) {
    if (e.incident_id !== incidentId) continue;
    view = applyEvent(view, e);
  }
  return view;
}

/** Folds every event into a per-incident map in one pass, for the ops
 * console feed (many incidents at once) and the metrics-adjacent views. */
export function foldAllIncidents(
  seeds: Record<string, Partial<IncidentView>>,
  events: EventEnvelope[],
): Record<string, IncidentView> {
  const views: Record<string, IncidentView> = {};
  for (const [id, seed] of Object.entries(seeds)) {
    views[id] = { ...emptyIncidentView(id), ...seed };
  }
  for (const e of events) {
    if (!e.incident_id || e.incident_id === "chaos") continue;
    const current = views[e.incident_id] ?? emptyIncidentView(e.incident_id);
    views[e.incident_id] = applyEvent(current, e);
  }
  return views;
}
