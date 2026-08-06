"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { OctagonX } from "lucide-react";

import { useReducedMotion } from "../hooks/useReducedMotion";
import { ApiError, postVeto } from "../lib/api";
import { signDecision } from "../lib/keys";
import type { ActionView } from "../lib/fold";
import { RadialCountdown } from "./RadialCountdown";

const VETO_WINDOW_SECONDS = 30;

/** plan/05-frontend.md, Approvals (overlay, not a route): "Yellow tier: a
 * veto card slides in bottom-right with a 30s radial countdown, the
 * action, the agent's reasoning, and a Veto button." */
export function VetoCard({ incidentId, action }: { incidentId: string; action: ActionView }) {
  const reducedMotion = useReducedMotion();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fingerprint, setFingerprint] = useState<string | null>(null);

  async function onVeto() {
    setSubmitting(true);
    setError(null);
    try {
      const signed = await signDecision(action.action_id, "veto");
      await postVeto(action.action_id, signed);
      setFingerprint(signed.pubkey.slice(0, 8));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "signing failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        role="alertdialog"
        aria-label="Veto window open"
        data-testid="veto-card"
        initial={reducedMotion ? false : { opacity: 0, x: 40 }}
        animate={{ opacity: 1, x: 0 }}
        exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: 40 }}
        transition={
          reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 260, damping: 24 }
        }
        className="fixed bottom-4 right-4 z-40 w-80 rounded-lg border p-3 shadow-2xl"
        style={{
          borderColor: "var(--aegis-warn)",
          background: "rgba(18,22,27,0.92)",
          backdropFilter: "blur(12px)",
        }}
      >
        <div className="flex items-start gap-3">
          {action.vetoClosesAt && (
            <RadialCountdown closesAt={action.vetoClosesAt} totalSeconds={VETO_WINDOW_SECONDS} />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium" style={{ color: "var(--aegis-warn)" }}>
              yellow tier, executing
            </p>
            <p className="mt-0.5 font-mono-data text-[11px]" style={{ color: "var(--aegis-text)" }}>
              {action.catalog_key}
              {action.params && Object.keys(action.params).length > 0
                ? ` ${JSON.stringify(action.params)}`
                : ""}
            </p>
            {action.reasoning && (
              <p className="mt-1 text-[11px]" style={{ color: "var(--aegis-text-secondary)" }}>
                {action.reasoning}
              </p>
            )}
            <p
              className="mt-1 font-mono-data text-[10px]"
              style={{ color: "var(--aegis-text-secondary)" }}
            >
              incident {incidentId}
            </p>
          </div>
        </div>

        {fingerprint ? (
          <p className="mt-2 font-mono-data text-[11px]" style={{ color: "var(--aegis-success)" }}>
            vetoed, signed {fingerprint}
          </p>
        ) : (
          <button
            type="button"
            onClick={onVeto}
            disabled={submitting}
            className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 text-xs font-medium transition-colors duration-200 disabled:opacity-50"
            style={{ borderColor: "var(--aegis-critical)", color: "var(--aegis-critical)" }}
          >
            <OctagonX size={13} aria-hidden />
            {submitting ? "signing..." : "veto"}
          </button>
        )}
        {error && (
          <p role="alert" className="mt-1 text-[11px]" style={{ color: "var(--aegis-critical)" }}>
            {error}
          </p>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
