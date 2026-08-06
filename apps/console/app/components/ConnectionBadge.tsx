"use client";

import { Wifi, WifiOff } from "lucide-react";

import { useConnectionStatus } from "../store/events";

const LABEL: Record<string, string> = {
  open: "live",
  connecting: "connecting",
  reconnecting: "reconnecting",
  closed: "offline",
};

const COLOR: Record<string, string> = {
  open: "var(--aegis-success)",
  connecting: "var(--aegis-text-secondary)",
  reconnecting: "var(--aegis-warn)",
  closed: "var(--aegis-critical)",
};

export function ConnectionBadge() {
  const status = useConnectionStatus();
  const Icon = status === "open" ? Wifi : WifiOff;
  const color = COLOR[status] ?? "var(--aegis-text-secondary)";

  return (
    <div
      className="flex items-center gap-1.5 font-mono-data text-[11px]"
      style={{ color }}
      role="status"
      aria-live="polite"
    >
      <Icon size={12} aria-hidden />
      {LABEL[status] ?? status}
    </div>
  );
}
