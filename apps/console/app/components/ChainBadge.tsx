"use client";

import { useEffect, useState } from "react";
import { ShieldCheck, ShieldX } from "lucide-react";

import { verifyChain } from "../lib/api";

export function ChainBadge({ incidentId }: { incidentId: string }) {
  const [result, setResult] = useState<
    { valid: boolean; break_at_seq: number | null } | "loading" | "error"
  >("loading");

  useEffect(() => {
    let cancelled = false;
    verifyChain(incidentId)
      .then((r) => {
        if (!cancelled) setResult(r);
      })
      .catch(() => {
        if (!cancelled) setResult("error");
      });
    return () => {
      cancelled = true;
    };
  }, [incidentId]);

  if (result === "loading") {
    return (
      <span className="font-mono-data text-[11px]" style={{ color: "var(--aegis-text-secondary)" }}>
        verifying chain...
      </span>
    );
  }
  if (result === "error") {
    return (
      <span className="font-mono-data text-[11px]" style={{ color: "var(--aegis-text-secondary)" }}>
        chain check unavailable
      </span>
    );
  }

  const Icon = result.valid ? ShieldCheck : ShieldX;
  const color = result.valid ? "var(--aegis-success)" : "var(--aegis-critical)";
  return (
    <span
      className="flex items-center gap-1.5 font-mono-data text-[11px]"
      style={{ color }}
      data-testid="chain-badge"
    >
      <Icon size={13} aria-hidden />
      {result.valid ? "chain verified" : `chain broken at seq ${result.break_at_seq}`}
    </span>
  );
}
