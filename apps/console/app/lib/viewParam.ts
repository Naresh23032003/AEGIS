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
