"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Skull, Zap } from "lucide-react";

import { ApiError, clearChaos, injectChaos } from "../lib/api";
import { activeScenarios } from "../lib/chaosState";
import { useVisibleEvents } from "../store/events";
import { SCENARIOS } from "./scenarios";

/** plan/05-frontend.md, Chaos Panel: "Style this screen like a weapons
 * console: it is the demo trigger and screenshots will circulate." */
export default function ChaosPanel() {
  const router = useRouter();
  const events = useVisibleEvents();
  const active = useMemo(() => activeScenarios(events), [events]);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function inject(scenario: string) {
    setPending(scenario);
    setError(null);
    try {
      // POST /api/chaos/{scenario} returns the chaos.injected envelope, not
      // an incident -- its incident_id is the synthetic "chaos" chain
      // (apps/core/aegis/api.py, CHAOS_CHAIN_ID), not a real one, since
      // detection hasn't opened an incident yet at inject time. The console
      // instead follows whichever incident is newest once one appears (see
      // OpsConsole's auto-follow effect).
      await injectChaos(scenario);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "injection failed");
    } finally {
      setPending(null);
    }
  }

  async function clear(scenario: string) {
    setPending(scenario);
    setError(null);
    try {
      await clearChaos(scenario);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "clear failed");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col gap-4 overflow-y-auto p-6">
      <div className="flex items-center gap-2">
        <Skull size={18} style={{ color: "var(--aegis-critical)" }} aria-hidden />
        <h1 className="text-sm font-semibold tracking-wide" style={{ color: "var(--aegis-text)" }}>
          chaos panel
        </h1>
      </div>

      {active.size > 0 && (
        <div className="rounded-md border p-3" style={{ borderColor: "var(--aegis-warn)" }}>
          <p className="text-[10px] uppercase tracking-wide" style={{ color: "var(--aegis-warn)" }}>
            active faults
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {[...active].map((scenario) => (
              <button
                key={scenario}
                type="button"
                data-testid={`clear-${scenario}`}
                onClick={() => clear(scenario)}
                disabled={pending === scenario}
                className="rounded-md border px-2 py-1 font-mono-data text-[11px] transition-colors duration-200 disabled:opacity-50"
                style={{ borderColor: "var(--aegis-warn)", color: "var(--aegis-warn)" }}
              >
                {scenario} · clear
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {SCENARIOS.map((scenario) => {
          const isActive = active.has(scenario.key);
          return (
            <div
              key={scenario.key}
              className="flex flex-col gap-2 rounded-lg border p-4"
              style={{
                borderColor: isActive ? "var(--aegis-critical)" : "var(--aegis-border)",
                background: "var(--aegis-surface)",
              }}
            >
              <p
                className="font-mono-data text-sm uppercase tracking-wide"
                style={{ color: "var(--aegis-text)" }}
              >
                {scenario.name}
              </p>
              <p className="text-xs" style={{ color: "var(--aegis-text-secondary)" }}>
                {scenario.breaks}
              </p>
              <p
                className="font-mono-data text-[11px]"
                style={{ color: "var(--aegis-text-secondary)" }}
              >
                expected: {scenario.expectedResponse}
              </p>
              <p className="font-mono-data text-[11px]" style={{ color: "var(--aegis-accent)" }}>
                fix path: {scenario.fixPath}
              </p>
              <button
                type="button"
                data-testid={`inject-${scenario.key}`}
                onClick={() => inject(scenario.key)}
                disabled={pending === scenario.key || isActive}
                className="mt-2 flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-200 disabled:opacity-50"
                style={{ background: "var(--aegis-critical)", color: "var(--aegis-bg)" }}
              >
                <Zap size={14} aria-hidden />
                {isActive
                  ? "already injected"
                  : pending === scenario.key
                    ? "injecting..."
                    : "inject fault"}
              </button>
            </div>
          );
        })}
      </div>

      {error && (
        <p role="alert" className="text-xs" style={{ color: "var(--aegis-critical)" }}>
          {error}
        </p>
      )}

      <p className="font-mono-data text-[11px]" style={{ color: "var(--aegis-text-secondary)" }}>
        safety: injections only touch the demo target stack (target-gateway, target-orders,
        target-payments, shop-db, redis, toxiproxy). Nothing outside deploy/docker-compose.yml is
        ever reachable from here.
      </p>
    </div>
  );
}
