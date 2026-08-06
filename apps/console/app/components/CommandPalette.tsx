"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import { AlertTriangle, ExternalLink, LayoutGrid, Search, Zap } from "lucide-react";

import { API_URL, injectChaos, listIncidents, type IncidentSummary } from "../lib/api";
import { VIEW_CHANGED_EVENT } from "../lib/viewParam";

const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL ?? "http://localhost:3001";

const SCENARIOS = ["latency", "crash", "error_spike", "memory_leak", "cache_outage"];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const router = useRouter();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") setOpen(false);
    };
    const onCustom = () => setOpen((o) => !o);
    window.addEventListener("keydown", onKey);
    window.addEventListener("aegis:open-palette", onCustom);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("aegis:open-palette", onCustom);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    listIncidents({ limit: 20 })
      .then(setIncidents)
      .catch(() => setIncidents([]));
  }, [open]);

  const close = useCallback(() => setOpen(false), []);

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command palette"
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
    >
      <div
        className="absolute inset-0"
        style={{ background: "rgba(5,6,7,0.7)" }}
        onClick={close}
        aria-hidden
      />
      <div
        className="relative w-full max-w-lg overflow-hidden rounded-lg border shadow-2xl"
        style={{
          borderColor: "var(--aegis-border)",
          background: "rgba(18,22,27,0.9)",
          backdropFilter: "blur(12px)",
        }}
      >
        <div
          className="flex items-center gap-2 border-b px-3 py-2"
          style={{ borderColor: "var(--aegis-border)" }}
        >
          <Search size={14} style={{ color: "var(--aegis-text-secondary)" }} aria-hidden />
          <Command.Input
            placeholder="Jump to incident, inject a scenario, open Grafana..."
            className="w-full bg-transparent py-1.5 text-sm outline-none font-mono-data"
            style={{ color: "var(--aegis-text)" }}
          />
        </div>
        <Command.List className="max-h-80 overflow-y-auto p-1.5">
          <Command.Empty
            className="px-3 py-4 text-xs"
            style={{ color: "var(--aegis-text-secondary)" }}
          >
            No matches.
          </Command.Empty>

          <Command.Group
            heading="View"
            className="px-2 py-1 text-[10px] uppercase tracking-wide"
            style={{ color: "var(--aegis-text-secondary)" }}
          >
            <PaletteItem
              icon={LayoutGrid}
              label="Toggle 2D / 3D topology"
              onSelect={() => {
                const url = new URL(window.location.href);
                const current = url.searchParams.get("view") ?? "3d";
                const next = current === "3d" ? "2d" : "3d";
                url.searchParams.set("view", next);
                router.push(url.pathname + url.search);
                window.dispatchEvent(new Event(VIEW_CHANGED_EVENT));
                close();
              }}
            />
            <PaletteItem
              icon={ExternalLink}
              label="Open Grafana"
              onSelect={() => {
                window.open(GRAFANA_URL, "_blank", "noopener,noreferrer");
                close();
              }}
            />
          </Command.Group>

          <Command.Group
            heading="Inject scenario"
            className="px-2 py-1 text-[10px] uppercase tracking-wide"
            style={{ color: "var(--aegis-text-secondary)" }}
          >
            {SCENARIOS.map((scenario) => (
              <PaletteItem
                key={scenario}
                icon={Zap}
                label={scenario.replace("_", " ")}
                onSelect={async () => {
                  close();
                  await injectChaos(scenario).catch(() => {});
                  router.push("/");
                }}
              />
            ))}
          </Command.Group>

          {incidents.length > 0 && (
            <Command.Group
              heading="Incidents"
              className="px-2 py-1 text-[10px] uppercase tracking-wide"
              style={{ color: "var(--aegis-text-secondary)" }}
            >
              {incidents.map((incident) => (
                <PaletteItem
                  key={incident.id}
                  icon={AlertTriangle}
                  label={incident.title}
                  meta={incident.status}
                  onSelect={() => {
                    close();
                    router.push(`/incidents/${incident.id}`);
                  }}
                />
              ))}
            </Command.Group>
          )}
        </Command.List>
        <div
          className="border-t px-3 py-1.5 text-[10px] font-mono-data"
          style={{ borderColor: "var(--aegis-border)", color: "var(--aegis-text-secondary)" }}
        >
          {API_URL}
        </div>
      </div>
    </Command.Dialog>
  );
}

function PaletteItem({
  icon: Icon,
  label,
  meta,
  onSelect,
}: {
  icon: typeof Zap;
  label: string;
  meta?: string;
  onSelect: () => void;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="flex cursor-pointer items-center justify-between gap-2 rounded-md px-2.5 py-2 text-sm data-[selected=true]:bg-[var(--aegis-surface-raised)]"
      style={{ color: "var(--aegis-text)" }}
    >
      <span className="flex items-center gap-2">
        <Icon size={13} style={{ color: "var(--aegis-accent)" }} aria-hidden />
        {label}
      </span>
      {meta && (
        <span
          className="font-mono-data text-[10px]"
          style={{ color: "var(--aegis-text-secondary)" }}
        >
          {meta}
        </span>
      )}
    </Command.Item>
  );
}
