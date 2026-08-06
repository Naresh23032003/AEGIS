"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, CircleGauge, DollarSign, ShieldCheck } from "lucide-react";

import { getMetricsSummary } from "../lib/api";
import type { MetricsSummary } from "../lib/types";
import { useVisibleEvents } from "../store/events";
import { CountUp } from "./CountUp";

const TERMINAL_TYPES = new Set(["incident.resolved", "incident.escalated"]);

/** plan/05-frontend.md, Ops Console: "Bottom strip: global MTTR ticker,
 * autonomy rate, active incident count, cost today, all from GET
 * /metrics/summary, animating on change with a count-up." Fetches once on
 * mount, then re-fetches only when a terminal event (resolved/escalated)
 * arrives on the store's already-open socket -- not a second poller.
 * plan/05, Frontend data layer: "No polling anywhere except the metrics
 * page (30s poll)." */
export function MetricsStrip() {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const events = useVisibleEvents();

  const terminalCount = useMemo(
    () => events.filter((e) => TERMINAL_TYPES.has(e.type)).length,
    [events],
  );

  useEffect(() => {
    let cancelled = false;
    getMetricsSummary()
      .then((s) => {
        if (!cancelled) setSummary(s);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [terminalCount]);

  const autonomyTotal = summary
    ? summary.autonomy.auto + summary.autonomy.approved + summary.autonomy.escalated
    : 0;
  const autonomyRate = autonomyTotal > 0 ? (summary!.autonomy.auto / autonomyTotal) * 100 : 0;

  return (
    <div
      className="flex h-11 shrink-0 items-center gap-6 border-t px-4 text-xs"
      style={{ borderColor: "var(--aegis-border)", background: "var(--aegis-surface)" }}
      data-testid="metrics-strip"
    >
      <Stat icon={CircleGauge} label="MTTR avg">
        <CountUp value={summary?.mttr_avg_seconds ?? 0} decimals={0} suffix="s" />
      </Stat>
      <Stat icon={ShieldCheck} label="autonomy (auto)">
        <CountUp value={autonomyRate} decimals={0} suffix="%" />
      </Stat>
      <Stat icon={Activity} label="active">
        <CountUp value={summary?.active_incidents ?? 0} decimals={0} />
      </Stat>
      <Stat icon={DollarSign} label="cost today">
        <CountUp value={summary?.cost_today_usd ?? 0} decimals={4} prefix="$" />
      </Stat>
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Activity;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon size={13} style={{ color: "var(--aegis-text-secondary)" }} aria-hidden />
      <span style={{ color: "var(--aegis-text-secondary)" }}>{label}</span>
      <span style={{ color: "var(--aegis-text)" }}>{children}</span>
    </div>
  );
}
