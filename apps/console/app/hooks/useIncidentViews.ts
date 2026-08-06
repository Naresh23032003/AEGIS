// Combines the REST-fetched incident list (initial fetch, per plan/05:
// "Server components for initial fetches; everything live is client-side
// from the store") with the live fold over the store's visible events, so
// incidents seeded before this page loaded still show correct titles and
// history, while status/actions/loop-ring state track the live stream.

"use client";

import { useEffect, useMemo, useState } from "react";

import { listIncidents, type IncidentSummary } from "../lib/api";
import { foldAllIncidents, type IncidentView } from "../lib/fold";
import { useVisibleEvents } from "../store/events";

function seedFromSummary(summary: IncidentSummary): Partial<IncidentView> {
  return {
    title: summary.title,
    severity: summary.severity,
    status: summary.status,
    sourceRule: summary.source_rule,
    affectedServices: summary.affected_services,
    summary: summary.summary,
    mttrSeconds: summary.mttr_seconds,
    autonomy: summary.autonomy,
    startedAt: summary.started_at,
    resolvedAt: summary.resolved_at,
  };
}

export function useIncidentViews(limit = 50): {
  views: Record<string, IncidentView>;
  ordered: IncidentView[];
  loading: boolean;
} {
  const [seeds, setSeeds] = useState<Record<string, Partial<IncidentView>>>({});
  const [loading, setLoading] = useState(true);
  const events = useVisibleEvents();

  useEffect(() => {
    let cancelled = false;
    listIncidents({ limit })
      .then((list) => {
        if (cancelled) return;
        setSeeds(Object.fromEntries(list.map((i) => [i.id, seedFromSummary(i)])));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [limit]);

  const views = useMemo(() => foldAllIncidents(seeds, events), [seeds, events]);
  const ordered = useMemo(
    () => Object.values(views).sort((a, b) => (b.startedAt ?? "").localeCompare(a.startedAt ?? "")),
    [views],
  );

  return { views, ordered, loading };
}
