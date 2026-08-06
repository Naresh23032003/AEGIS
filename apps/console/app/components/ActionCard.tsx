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
      {action.confidence != null && (
        <p className="font-mono-data" style={{ color: "var(--aegis-text-secondary)" }}>
          confidence {(action.confidence * 100).toFixed(0)}%
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
