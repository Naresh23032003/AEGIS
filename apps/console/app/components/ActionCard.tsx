// Both confidences are shown, labelled. The card used to render only the
// action's own number under a bare "confidence", which read as the
// system's confidence in the whole incident. On
// error_spike_target-gateway the diagnosis sits at 0.0 and the action at
// 0.8; a viewer who saw one number saw the flattering one.
//
// Both guards are `!= null`, not truthiness: 0.0 is a real answer (the
// model restated the symptom instead of naming a cause) and has to render
// as `diagnosis 0%`. It carries text-secondary like every other field
// here, so zero looks like a measurement rather than a failed read.

import type { ActionView } from "../lib/fold";

const TIER_COLOR: Record<string, string> = {
  green: "var(--aegis-success)",
  yellow: "var(--aegis-warn)",
  red: "var(--aegis-critical)",
};

const STATUS_LABEL: Record<string, string> = {
  proposed: "proposed",
  denied: "denied by policy",
  veto_open: "executing, veto window open",
  awaiting_approval: "awaiting approval",
  executing: "executing",
  executed: "executed",
  failed: "failed",
  vetoed: "vetoed",
  rejected: "rejected",
  rolled_back: "rolled back",
};

export function ActionCard({ action }: { action: ActionView }) {
  const tierColor = action.tier ? TIER_COLOR[action.tier] : "var(--aegis-text-secondary)";

  return (
    <div
      data-testid="action-card"
      className="rounded-md border p-2 text-[11px]"
      style={{ borderColor: "var(--aegis-border)" }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono-data" style={{ color: "var(--aegis-text)" }}>
          {action.catalog_key ?? action.action_id}
        </span>
        {action.tier && (
          <span
            className="rounded-full px-1.5 py-0.5 font-mono-data text-[9px] uppercase"
            style={{ color: tierColor, border: `1px solid ${tierColor}` }}
          >
            {action.tier}
          </span>
        )}
      </div>
      <p style={{ color: "var(--aegis-text-secondary)" }}>
        {STATUS_LABEL[action.status] ?? action.status}
      </p>
      {(action.diagnosisConfidence != null || action.confidence != null) && (
        <p className="flex gap-3 font-mono-data" style={{ color: "var(--aegis-text-secondary)" }}>
          {action.diagnosisConfidence != null && (
            <span data-testid="diagnosis-confidence">
              diagnosis {(action.diagnosisConfidence * 100).toFixed(0)}%
            </span>
          )}
          {action.confidence != null && (
            <span data-testid="action-confidence">
              action {(action.confidence * 100).toFixed(0)}%
            </span>
          )}
        </p>
      )}
      {action.reasoning && (
        <p style={{ color: "var(--aegis-text-secondary)" }}>{action.reasoning}</p>
      )}
      {action.opaRuleId && (
        <p className="font-mono-data" style={{ color: "var(--aegis-text-secondary)" }}>
          opa: {action.opaRuleId}
        </p>
      )}
      {action.decidedBy && (
        <p className="font-mono-data" style={{ color: "var(--aegis-text-secondary)" }}>
          signed {action.decidedBy.slice(0, 8) || "system"}
        </p>
      )}
      {action.rejectReason && (
        <p style={{ color: "var(--aegis-critical)" }}>{action.rejectReason}</p>
      )}
    </div>
  );
}
