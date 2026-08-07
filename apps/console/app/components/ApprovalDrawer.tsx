"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ShieldAlert, X } from "lucide-react";

import { useReducedMotion } from "../hooks/useReducedMotion";
import { ApiError, postApproval } from "../lib/api";
import { signDecision } from "../lib/keys";
import type { ActionView } from "../lib/fold";

/** plan/05-frontend.md, Approvals (overlay, not a route): "Red tier: a
 * blocking approval drawer from the right with reasoning, evidence refs,
 * the exact command diff, and Approve / Reject." Evidence refs: plan/02's
 * event catalog has no event carrying the diagnose node's evidence list
 * (only verify.passed/failed do, after the fact); action.approval_requested
 * only has {action_id, diff, reasoning}, so this drawer shows the diff and
 * reasoning it actually has rather than fabricating an evidence list. See
 * docs/reports/PHASE_4_REPORT.md, Deviations.
 *
 * Focus, per plan/05's data-layer rules: the drawer takes initial focus on
 * mount and traps focus while it is open. Before that it was an
 * alertdialog sitting at the end of the tab order behind the whole
 * incident feed, which the final verification pass reached only after 59
 * Tab presses (defect 5's second half, docs/reports/FINAL_VERIFICATION.md).
 * Focus lands on the drawer itself rather than on approve, so the reading
 * order starts at the diff and one Tab reaches the first control; putting
 * it straight on approve would make a stray Enter execute a red-tier
 * action. */
const FOCUSABLE =
  'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function ApprovalDrawer({ incidentId, action }: { incidentId: string; action: ActionView }) {
  const reducedMotion = useReducedMotion();
  const [submitting, setSubmitting] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decided, setDecided] = useState<{ decision: string; fingerprint: string } | null>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const restoreTo = document.activeElement as HTMLElement | null;
    drawerRef.current?.focus();
    return () => restoreTo?.focus?.();
  }, []);

  const trapFocus = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Tab") return;
    const root = drawerRef.current;
    if (!root) return;
    const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
    const first = items[0];
    const last = items[items.length - 1];
    if (first === undefined || last === undefined) {
      event.preventDefault(); // nothing left to move to, e.g. after deciding
      return;
    }
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === root)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }, []);

  async function decide(decision: "approve" | "reject") {
    setSubmitting(decision);
    setError(null);
    try {
      const signed = await signDecision(action.action_id, decision);
      await postApproval(action.action_id, signed);
      setDecided({ decision, fingerprint: signed.pubkey.slice(0, 8) });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "signing failed");
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        ref={drawerRef}
        role="alertdialog"
        aria-modal="true"
        aria-label="Red tier action awaiting approval"
        data-testid="approval-drawer"
        tabIndex={-1}
        onKeyDown={trapFocus}
        initial={reducedMotion ? false : { opacity: 0, x: 60 }}
        animate={{ opacity: 1, x: 0 }}
        exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: 60 }}
        transition={
          reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 260, damping: 24 }
        }
        className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l p-4 shadow-2xl"
        style={{
          borderColor: "var(--aegis-critical)",
          background: "rgba(11,14,17,0.96)",
          backdropFilter: "blur(12px)",
        }}
      >
        <div className="flex items-center gap-2">
          <ShieldAlert size={16} style={{ color: "var(--aegis-critical)" }} aria-hidden />
          <p className="text-sm font-semibold" style={{ color: "var(--aegis-critical)" }}>
            red tier, approval required
          </p>
        </div>
        <p
          className="mt-1 font-mono-data text-[11px]"
          style={{ color: "var(--aegis-text-secondary)" }}
        >
          incident {incidentId} · action {action.action_id}
        </p>

        <div className="mt-4">
          <p
            className="text-[10px] uppercase tracking-wide"
            style={{ color: "var(--aegis-text-secondary)" }}
          >
            command diff
          </p>
          <pre
            className="mt-1 overflow-x-auto rounded-md border p-2 font-mono-data text-[11px]"
            style={{ borderColor: "var(--aegis-border)", color: "var(--aegis-text)" }}
          >
            {JSON.stringify(
              action.approvalDiff ?? { catalog_key: action.catalog_key, params: action.params },
              null,
              2,
            )}
          </pre>
        </div>

        {action.approvalReasoning && (
          <div className="mt-4">
            <p
              className="text-[10px] uppercase tracking-wide"
              style={{ color: "var(--aegis-text-secondary)" }}
            >
              agent reasoning
            </p>
            <p className="mt-1 text-xs" style={{ color: "var(--aegis-text)" }}>
              {action.approvalReasoning}
            </p>
          </div>
        )}

        <div className="mt-auto flex flex-col gap-2 pt-4">
          {decided ? (
            <p className="font-mono-data text-xs" style={{ color: "var(--aegis-success)" }}>
              {decided.decision}d, signed {decided.fingerprint}
            </p>
          ) : (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => decide("approve")}
                disabled={submitting !== null}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-200 disabled:opacity-50"
                style={{ background: "var(--aegis-success)", color: "var(--aegis-bg)" }}
              >
                <Check size={14} aria-hidden />
                {submitting === "approve" ? "signing..." : "approve"}
              </button>
              <button
                type="button"
                onClick={() => decide("reject")}
                disabled={submitting !== null}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition-colors duration-200 disabled:opacity-50"
                style={{ borderColor: "var(--aegis-critical)", color: "var(--aegis-critical)" }}
              >
                <X size={14} aria-hidden />
                {submitting === "reject" ? "signing..." : "reject"}
              </button>
            </div>
          )}
          {error && (
            <p role="alert" className="text-[11px]" style={{ color: "var(--aegis-critical)" }}>
              {error}
            </p>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
