// Shared by TopologyRenderer (reads it) and CommandPalette (writes it via
// router.push, then dispatches VIEW_CHANGED_EVENT) so the two don't need
// to import each other just for this one constant and helper.

export type ViewParam = "2d" | "3d" | null;

export const VIEW_CHANGED_EVENT = "aegis:view-changed";

export function readViewParam(): ViewParam {
  if (typeof window === "undefined") return null;
  const v = new URLSearchParams(window.location.search).get("view");
  return v === "2d" || v === "3d" ? v : null;
}

/** Carries an explicit ?view= override across an in-app navigation. Without
 * it the override only survives while you stay on one route: the chaos panel
 * pushes to "/" right after injecting, so someone who forced ?view=2d
 * (a machine whose WebGL is broken, the reason the override exists) landed
 * back on the 3D canvas the moment they triggered the demo. Found by the
 * final verification UI walkthrough, docs/reports/FINAL_VERIFICATION.md. */
export function withViewParam(path: string): string {
  const view = readViewParam();
  return view ? `${path}?view=${view}` : path;
}
