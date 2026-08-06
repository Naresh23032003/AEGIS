"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getMetricsSummary } from "../lib/api";
import type { MetricsSummary } from "../lib/types";

const POLL_MS = 30_000;

const AUTONOMY_COLORS: Record<string, string> = {
  auto: "var(--aegis-success)",
  approved: "var(--aegis-accent)",
  escalated: "var(--aegis-critical)",
};

const CHART_TEXT = "var(--aegis-text-secondary)";
const CHART_GRID = "var(--aegis-border)";

/** plan/05-frontend.md, Metrics: "MTTR trend (line, per scenario),
 * autonomy split (auto / approved / escalated), cost per incident, loop
 * iterations histogram. Recharts, no 3D here." plan/05, Frontend data
 * layer: "No polling anywhere except the metrics page (30s poll)." -- the
 * one deliberate exception to the store-only rule. */
export default function MetricsPage() {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    function load() {
      getMetricsSummary()
        .then((s) => {
          if (!cancelled) setSummary(s);
        })
        .catch(() => {});
    }
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!summary) {
    return (
      <div className="p-6">
        <p className="text-xs" style={{ color: "var(--aegis-text-secondary)" }}>
          loading metrics...
        </p>
      </div>
    );
  }

  const mttrData = summary.mttr_trend.map((m) => ({
    label: m.incident_id.slice(-6),
    source_rule: m.source_rule,
    mttr: m.mttr_seconds,
  }));
  const costData = summary.cost_per_incident.map((c) => ({
    label: c.incident_id.slice(-6),
    source_rule: c.source_rule,
    cost: c.cost_usd,
  }));
  const loopBuckets: Record<number, number> = {};
  for (const l of summary.loop_iterations) {
    loopBuckets[l.loops] = (loopBuckets[l.loops] ?? 0) + 1;
  }
  const loopData = Object.entries(loopBuckets)
    .map(([loops, count]) => ({ loops: Number(loops), count }))
    .sort((a, b) => a.loops - b.loops);
  const autonomyData = (["auto", "approved", "escalated"] as const).map((key) => ({
    key,
    value: summary.autonomy[key],
  }));

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-6">
      <h1 className="text-sm font-semibold tracking-wide" style={{ color: "var(--aegis-text)" }}>
        metrics
      </h1>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ChartCard title="MTTR trend (seconds, per incident)">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={mttrData}>
              <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" />
              <XAxis dataKey="label" stroke={CHART_TEXT} fontSize={10} />
              <YAxis stroke={CHART_TEXT} fontSize={10} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line
                type="monotone"
                dataKey="mttr"
                stroke="var(--aegis-accent)"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title={`autonomy split (escalation rate ${(summary.escalation_rate * 100).toFixed(0)}%)`}
        >
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={autonomyData}
                dataKey="value"
                nameKey="key"
                innerRadius={50}
                outerRadius={80}
              >
                {autonomyData.map((entry) => (
                  <Cell key={entry.key} fill={AUTONOMY_COLORS[entry.key]} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 font-mono-data text-[11px]">
            {autonomyData.map((entry) => (
              <span key={entry.key} style={{ color: AUTONOMY_COLORS[entry.key] }}>
                {entry.key} {entry.value}
              </span>
            ))}
          </div>
        </ChartCard>

        <ChartCard title="cost per incident (USD)">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={costData}>
              <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" />
              <XAxis dataKey="label" stroke={CHART_TEXT} fontSize={10} />
              <YAxis stroke={CHART_TEXT} fontSize={10} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="cost" fill="var(--aegis-success)" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="loop iterations (verify attempts per incident)">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={loopData}>
              <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" />
              <XAxis dataKey="loops" stroke={CHART_TEXT} fontSize={10} />
              <YAxis stroke={CHART_TEXT} fontSize={10} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" fill="var(--aegis-warn)" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}

const tooltipStyle = {
  background: "var(--aegis-surface-raised)",
  border: "1px solid var(--aegis-border)",
  borderRadius: 6,
  fontSize: 11,
  color: "var(--aegis-text)",
};

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border p-4" style={{ borderColor: "var(--aegis-border)" }}>
      <p
        className="mb-2 text-[10px] uppercase tracking-wide"
        style={{ color: "var(--aegis-text-secondary)" }}
      >
        {title}
      </p>
      {children}
    </div>
  );
}
