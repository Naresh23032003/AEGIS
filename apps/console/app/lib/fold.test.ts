import { describe, expect, it } from "vitest";

import { foldAllIncidents, foldIncidentEvents } from "./fold";
import type { EventEnvelope } from "./types";

function ev(
  type: string,
  payload: Record<string, unknown>,
  overrides: Partial<EventEnvelope> = {},
): EventEnvelope {
  return {
    id: overrides.id ?? `evt_${Math.random().toString(36).slice(2)}`,
    ts: overrides.ts ?? "2026-08-06T10:00:00.000Z",
    type,
    incident_id: overrides.incident_id ?? "inc_1",
    actor: overrides.actor ?? "system:detector",
    payload,
  };
}

describe("foldIncidentEvents", () => {
  it("is a pure function: same events in, same view out, no mutation of the input array", () => {
    const events = [
      ev("incident.detected", { rule: "service_down", service: "target-payments" }),
      ev("incident.classified", {
        severity: "sev2",
        affected_services: ["target-payments"],
        summary: "payments down",
      }),
    ];
    const frozen = JSON.parse(JSON.stringify(events));
    const a = foldIncidentEvents("inc_1", undefined, events);
    const b = foldIncidentEvents("inc_1", undefined, events);
    expect(events).toEqual(frozen);
    expect(a).toEqual(b);
  });

  it("synthesizes a title from rule + service when no REST seed exists", () => {
    const view = foldIncidentEvents("inc_1", undefined, [
      ev("incident.detected", { rule: "service_down", service: "target-payments" }),
    ]);
    expect(view.title).toBe("service_down on target-payments");
  });

  it("prefers a REST-seeded title over the synthesized one", () => {
    const view = foldIncidentEvents("inc_1", { title: "payments is down (real title)" }, [
      ev("incident.detected", { rule: "service_down", service: "target-payments" }),
    ]);
    expect(view.title).toBe("payments is down (real title)");
  });

  it("ignores events addressed to a different incident", () => {
    const view = foldIncidentEvents("inc_1", undefined, [
      ev(
        "incident.classified",
        { severity: "sev1", affected_services: ["x"], summary: "wrong incident" },
        { incident_id: "inc_2" },
      ),
    ]);
    expect(view.severity).toBeNull();
  });

  it("walks the full graph: triage -> diagnose -> plan -> gate(green) -> execute -> verify -> resolve", () => {
    const events: EventEnvelope[] = [
      ev("incident.detected", { rule: "service_down", service: "target-payments" }),
      ev(
        "agent.run.started",
        { agent: "triage", model: "m", checkpoint_id: "inc_1" },
        { actor: "agent:triage" },
      ),
      ev("incident.classified", {
        severity: "sev2",
        affected_services: ["target-payments"],
        summary: "s",
      }),
      ev("agent.run.completed", {
        agent: "triage",
        tokens_in: 1,
        tokens_out: 1,
        cost_usd: 0.0001,
        duration_ms: 100,
      }),
      ev("agent.run.started", { agent: "diagnose", model: "m", checkpoint_id: "inc_1" }),
      ev("agent.run.completed", {
        agent: "diagnose",
        tokens_in: 1,
        tokens_out: 1,
        cost_usd: 0.0002,
        duration_ms: 200,
      }),
      ev("agent.run.started", { agent: "plan_remediation", model: "m", checkpoint_id: "inc_1" }),
      ev("action.proposed", {
        action_id: "act_1",
        catalog_key: "restart_service",
        params: { service: "target-payments" },
        tier: "green",
        confidence: 0.9,
        reasoning: "r",
        rollback_key: null,
      }),
      ev("agent.run.completed", {
        agent: "plan_remediation",
        tokens_in: 1,
        tokens_out: 1,
        cost_usd: 0.0003,
        duration_ms: 300,
      }),
      ev("action.policy_checked", {
        action_id: "act_1",
        decision: "allow",
        opa_rule_id: "allow_green_tier",
      }),
      ev("action.executed", {
        action_id: "act_1",
        catalog_key: "restart_service",
        params: { service: "target-payments" },
        result: { action: "restart" },
        status: "executed",
        duration_ms: 50,
      }),
      ev("agent.run.started", { agent: "verify", model: "m", checkpoint_id: "inc_1" }),
      ev("verify.passed", { evidence: [] }),
      ev("agent.run.completed", {
        agent: "verify",
        tokens_in: 1,
        tokens_out: 1,
        cost_usd: 0.0001,
        duration_ms: 80,
      }),
      ev("incident.resolved", { mttr_seconds: 12, autonomy: "auto", actions_taken: ["act_1"] }),
    ];

    const view = foldIncidentEvents("inc_1", undefined, events);

    expect(view.status).toBe("resolved");
    expect(view.mttrSeconds).toBe(12);
    expect(view.autonomy).toBe("auto");
    expect(view.activeAgents).toEqual([]);
    expect([...view.loopPhases].sort()).toEqual(["act", "observe", "plan", "verify"]);
    expect(view.actions["act_1"]!.status).toBe("executed");
    expect(view.actions["act_1"]!.policyDecision).toBe("allow");
    expect(view.agentRuns["diagnose"]!.status).toBe("completed");
  });

  it("marks a yellow-tier action vetoed, not merely rejected, when action.rejected follows a veto window", () => {
    const events: EventEnvelope[] = [
      ev("action.proposed", {
        action_id: "act_2",
        catalog_key: "scale_service",
        params: {},
        tier: "yellow",
        confidence: 0.8,
        reasoning: "r",
        rollback_key: "scale_service",
      }),
      ev("action.policy_checked", {
        action_id: "act_2",
        decision: "allow",
        opa_rule_id: "allow_yellow_tier",
      }),
      ev("action.veto_window_opened", {
        action_id: "act_2",
        closes_at: "2026-08-06T10:00:30.000Z",
      }),
      ev(
        "action.rejected",
        {
          action_id: "act_2",
          approver_pubkey: "abc123",
          signature: "sig",
          reason: "vetoed during the veto window",
        },
        { actor: "human:abc12345" },
      ),
    ];
    const view = foldIncidentEvents("inc_1", undefined, events);
    expect(view.actions["act_2"]!.status).toBe("vetoed");
  });

  it("marks a red-tier action rejected (not vetoed) when there was no veto window", () => {
    const events: EventEnvelope[] = [
      ev("action.proposed", {
        action_id: "act_3",
        catalog_key: "restart_database",
        params: {},
        tier: "red",
        confidence: 0.7,
        reasoning: "r",
        rollback_key: null,
      }),
      ev("action.approval_requested", {
        action_id: "act_3",
        diff: { catalog_key: "restart_database", params: {} },
        reasoning: "r",
      }),
      ev(
        "action.rejected",
        {
          action_id: "act_3",
          approver_pubkey: "",
          signature: "",
          reason: "15 minute approval window expired unanswered",
        },
        { actor: "system:supervisor" },
      ),
    ];
    const view = foldIncidentEvents("inc_1", undefined, events);
    expect(view.actions["act_3"]!.status).toBe("rejected");
  });

  it("records agent.quarantined and incident.escalated", () => {
    const events: EventEnvelope[] = [
      ev("agent.quarantined", {
        agent: "diagnose",
        reason: "missed 3 heartbeats",
        recovery: "resume",
      }),
      ev("incident.escalated", { reason: "loop_count exceeded max 3", loops_exhausted: true }),
    ];
    const view = foldIncidentEvents("inc_1", undefined, events);
    expect(view.quarantine).toEqual({
      agent: "diagnose",
      reason: "missed 3 heartbeats",
      recovery: "resume",
    });
    expect(view.status).toBe("escalated");
    expect(view.escalation).toEqual({ reason: "loop_count exceeded max 3", loopsExhausted: true });
  });
});

describe("foldAllIncidents", () => {
  it("buckets events by incident_id and ignores the synthetic chaos chain", () => {
    const events: EventEnvelope[] = [
      ev(
        "incident.detected",
        { rule: "service_down", service: "target-payments" },
        { incident_id: "inc_a" },
      ),
      ev(
        "incident.detected",
        { rule: "error_rate", service: "target-payments" },
        { incident_id: "inc_b" },
      ),
      ev("chaos.injected", { scenario: "crash", params: {} }, { incident_id: "chaos" }),
    ];
    const views = foldAllIncidents({}, events);
    expect(Object.keys(views).sort()).toEqual(["inc_a", "inc_b"]);
  });

  it("produces the same per-incident view as foldIncidentEvents run alone", () => {
    const events: EventEnvelope[] = [
      ev(
        "incident.detected",
        { rule: "service_down", service: "target-payments" },
        { incident_id: "inc_a" },
      ),
      ev(
        "incident.classified",
        { severity: "sev2", affected_services: ["target-payments"], summary: "s" },
        { incident_id: "inc_a" },
      ),
      ev(
        "incident.detected",
        { rule: "error_rate", service: "target-orders" },
        { incident_id: "inc_b" },
      ),
    ];
    const all = foldAllIncidents({}, events);
    const alone = foldIncidentEvents("inc_a", undefined, events);
    expect(all["inc_a"]).toEqual(alone);
  });
});
