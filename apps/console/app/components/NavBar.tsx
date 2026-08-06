"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BarChart3, Command, ShieldCheck, Zap } from "lucide-react";

import { ConnectionBadge } from "./ConnectionBadge";

const LINKS = [
  { href: "/", label: "console", icon: Activity },
  { href: "/chaos", label: "chaos", icon: Zap },
  { href: "/metrics", label: "metrics", icon: BarChart3 },
];

export function NavBar() {
  const pathname = usePathname();

  return (
    <header
      className="flex h-12 w-full shrink-0 items-center justify-between overflow-hidden border-b px-3 sm:px-4"
      style={{ borderColor: "var(--aegis-border)", background: "var(--aegis-surface)" }}
    >
      <div className="flex min-w-0 items-center gap-3 sm:gap-6">
        <Link href="/" className="flex shrink-0 items-center gap-2 focus-visible:outline-none">
          <ShieldCheck size={18} style={{ color: "var(--aegis-accent)" }} aria-hidden />
          <span className="font-mono-data text-sm font-semibold tracking-wide">AEGIS</span>
        </Link>
        <nav className="hidden items-center gap-1 sm:flex" aria-label="Primary">
          {LINKS.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs transition-colors duration-200"
                style={{
                  color: active ? "var(--aegis-text)" : "var(--aegis-text-secondary)",
                  background: active ? "var(--aegis-surface-raised)" : "transparent",
                }}
              >
                <Icon size={13} aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
      <div className="flex shrink-0 items-center gap-2 sm:gap-3">
        <button
          type="button"
          onClick={() => window.dispatchEvent(new CustomEvent("aegis:open-palette"))}
          className="hidden items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] transition-colors duration-200 sm:flex"
          style={{ borderColor: "var(--aegis-border)", color: "var(--aegis-text-secondary)" }}
        >
          <Command size={12} aria-hidden />
          <span className="font-mono-data">K</span>
        </button>
        <ConnectionBadge />
      </div>
    </header>
  );
}
