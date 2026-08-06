"use client";

import { useEffect, useRef, useState } from "react";

import { DetailPanel } from "./components/DetailPanel";
import { IncidentFeed } from "./components/IncidentFeed";
import { MetricsStrip } from "./components/MetricsStrip";
import { TopologyRenderer } from "./components/TopologyRenderer";
import { useIncidentViews } from "./hooks/useIncidentViews";

const TERMINAL_STATUSES = new Set(["resolved", "escalated"]);

export default function OpsConsole() {
  const { ordered, views, loading } = useIncidentViews();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const pinnedRef = useRef(false);

  // Auto-follows the newest incident, e.g. right after injecting from
  // /chaos (plan/05-frontend.md, Chaos Panel: "navigates to the console
  // with the new incident focused" -- there is no incident id to focus at
  // inject time, detection has not opened one yet, see app/chaos/page.tsx,
  // so the console follows the newest one once it appears instead). A
  // manual click pins the selection until that incident resolves or the
  // user clicks another card.
  useEffect(() => {
    const newest = ordered[0];
    if (!newest) return;
    setSelectedId((current) => {
      if (!current) return newest.id;
      if (current === newest.id) return current;
      const currentView = views[current];
      const currentIsTerminal = !currentView || TERMINAL_STATUSES.has(currentView.status);
      if (!pinnedRef.current && currentIsTerminal) return newest.id;
      return current;
    });
  }, [ordered, views]);

  function selectManually(id: string) {
    pinnedRef.current = true;
    setSelectedId(id);
  }

  const selected = selectedId ? views[selectedId] : undefined;

  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1">
        <aside
          className="flex w-80 shrink-0 flex-col border-r"
          style={{ borderColor: "var(--aegis-border)" }}
          aria-label="Incident feed"
        >
          <IncidentFeed
            incidents={ordered}
            selectedId={selectedId}
            onSelect={selectManually}
            loading={loading}
          />
        </aside>

        <main className="min-w-0 flex-1" aria-label="Topology">
          <TopologyRenderer />
        </main>

        {selected && (
          <aside
            className="w-[400px] shrink-0 border-l"
            style={{ borderColor: "var(--aegis-border)" }}
            aria-label="Incident detail"
          >
            <DetailPanel
              incident={selected}
              onClose={() => {
                pinnedRef.current = false;
                setSelectedId(null);
              }}
            />
          </aside>
        )}
      </div>
      <MetricsStrip />
    </div>
  );
}
