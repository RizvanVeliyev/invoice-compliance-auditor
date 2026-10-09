"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertSummary, api } from "@/lib/api";

const LINKS = [
  { href: "/submit", label: "Submit an invoice" },
  { href: "/audit", label: "Audit desk" },
  { href: "/check", label: "Quick check" },
];

export default function Nav() {
  const path = usePathname();
  const [unread, setUnread] = useState<number | null>(null);

  // The bell is a convenience: it shows only when the auditor endpoints are reachable
  // (no PIN configured, or a PIN already entered in this tab).
  useEffect(() => {
    let alive = true;
    const tick = () =>
      api<AlertSummary>("/api/alerts/summary", {}, true)
        .then((s) => alive && setUnread(s.unread))
        .catch(() => alive && setUnread(null));
    tick();
    const t = setInterval(tick, 8000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [path]);

  return (
    <header className="nav">
      <Link href="/" className="wordmark" aria-label="Ledger home">
        <span className="wordmark-rule" aria-hidden />
        Ledger
      </Link>
      <nav className="nav-links" aria-label="Main">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className={`nav-link${path?.startsWith(l.href) ? " is-active" : ""}`}>
            {l.label}
            {l.href === "/audit" && unread !== null && unread > 0 && (
              <span className="bell" aria-label={`${unread} new alerts`}>
                {unread}
              </span>
            )}
          </Link>
        ))}
      </nav>
    </header>
  );
}
