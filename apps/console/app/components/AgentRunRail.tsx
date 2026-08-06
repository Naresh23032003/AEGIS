import { ExternalLink } from "lucide-react";

import type { AgentRunView } from "../lib/fold";

const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL ?? "http://localhost:3001";

const STATUS_COLOR: Record<string, string> = {
  running: "var(--aegis-accent)",
  completed: "var(--aegis-success)",
  failed: "var(--aegis-critical)",
};

export function AgentRunRail({ runs }: { runs: Record<string, AgentRunView> }) {
  const ordered = Object.values(runs);
  const totalCost = ordered.reduce((sum, r) => sum + (r.costUsd ?? 0), 0);

  return (
    <div className="flex flex-col gap-2 p-3" data-testid="agent-run-rail">
      <div className="flex items-center justify-between">
        <p
          className="text-[10px] uppercase tracking-wide"
          style={{ color: "var(--aegis-text-secondary)" }}
        >
          agent runs
        </p>
        <p className="font-mono-data text-[11px]" style={{ color: "var(--aegis-text)" }}>
          ${totalCost.toFixed(5)}
        </p>
      </div>
      {ordered.length === 0 && (
        <p className="font-mono-data text-[11px]" style={{ color: "var(--aegis-text-secondary)" }}>
          no runs yet
        </p>
      )}
      {ordered.map((run) => (
        <div
          key={run.agent}
          className="rounded-md border p-2 text-[11px]"
          style={{ borderColor: "var(--aegis-border)" }}
        >
          <div className="flex items-center justify-between">
            <span className="font-mono-data" style={{ color: "var(--aegis-text)" }}>
              {run.agent}
            </span>
            <span className="font-mono-data" style={{ color: STATUS_COLOR[run.status] }}>
              {run.status}
            </span>
          </div>
          {run.model && (
            <p className="font-mono-data" style={{ color: "var(--aegis-text-secondary)" }}>
              {run.model}
            </p>
          )}
          <p className="font-mono-data" style={{ color: "var(--aegis-text-secondary)" }}>
            {run.tokensIn ?? 0}in / {run.tokensOut ?? 0}out · ${(run.costUsd ?? 0).toFixed(5)} ·{" "}
            {run.durationMs ?? 0}ms
          </p>
          {run.reason && <p style={{ color: "var(--aegis-critical)" }}>{run.reason}</p>}
        </div>
      ))}
      <a
        href={GRAFANA_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1 flex items-center gap-1 font-mono-data text-[11px] transition-colors duration-200"
        style={{ color: "var(--aegis-accent)" }}
      >
        raw traces in Grafana
        <ExternalLink size={11} aria-hidden />
      </a>
    </div>
  );
}
