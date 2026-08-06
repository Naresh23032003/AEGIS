"use client";

import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";

const BREAKPOINT = "(max-width: 767px)";

/** plan/05-frontend.md, Hard rules: "Responsive at 1440, 1024, 768; below
 * 768 show a 'best on desktop' simplified read-only view, do not attempt
 * full mobile." The three-column ops console, the topology canvas, and
 * the flight recorder scrubber are all built for a wide viewport; below
 * the 768px breakpoint this gate replaces them with a single static
 * notice instead of a broken layout. */
export function DesktopOnlyGate({ children }: { children: React.ReactNode }) {
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    const query = window.matchMedia(BREAKPOINT);
    setNarrow(query.matches);
    const onChange = (e: MediaQueryListEvent) => setNarrow(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  if (!narrow) return <>{children}</>;

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <ShieldCheck size={28} style={{ color: "var(--aegis-accent)" }} aria-hidden />
      <p className="text-sm" style={{ color: "var(--aegis-text)" }}>
        AEGIS is best on desktop
      </p>
      <p className="max-w-xs text-xs" style={{ color: "var(--aegis-text-secondary)" }}>
        The topology view, flight recorder scrubber, and approval flows need a wider screen. Reopen
        this at 768px or wider.
      </p>
    </div>
  );
}
