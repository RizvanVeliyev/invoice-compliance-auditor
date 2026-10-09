"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Icon, { Avatar } from "@/components/Icon";
import ThemeToggle from "@/components/ThemeToggle";
import { AlertSummary, api, isAuditor, Role } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LanguageSwitch, useI18n } from "@/lib/i18n";

const LINKS: { href: string; label: string; icon: string; roles?: Role[] }[] = [
  { href: "/submit", label: "nav.submit", icon: "upload" },
  { href: "/my", label: "nav.my", icon: "file" },
  { href: "/audit", label: "nav.audit", icon: "inbox", roles: ["auditor", "admin"] },
  { href: "/employees", label: "nav.employees", icon: "people", roles: ["auditor", "admin"] },
  { href: "/overview", label: "nav.overview", icon: "chart", roles: ["auditor", "admin"] },
  { href: "/users", label: "nav.accounts", icon: "key", roles: ["admin"] },
  { href: "/check", label: "nav.check", icon: "bolt" },
];

export default function Nav() {
  const path = usePathname();
  const router = useRouter();
  const { t } = useI18n();
  const { user, loading, signOut } = useAuth();
  const [unread, setUnread] = useState<number | null>(null);
  const [pending, setPending] = useState(0);
  const auditor = isAuditor(user);
  const admin = user?.role === "admin";

  // People waiting for auditor access, next to "Accounts" for the admin.
  useEffect(() => {
    if (!admin) {
      setPending(0);
      return;
    }
    let alive = true;
    const tick = () =>
      api<{ pending: number }>("/api/users/pending")
        .then((p) => alive && setPending(p.pending))
        .catch(() => {});
    tick();
    const timer = setInterval(tick, 8000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [path, admin]);

  // Unread alerts next to "Audit desk", for the people who can open it.
  useEffect(() => {
    if (!auditor) {
      setUnread(null);
      return;
    }
    let alive = true;
    const tick = () =>
      api<AlertSummary>("/api/alerts/summary")
        .then((s) => alive && setUnread(s.unread))
        .catch(() => alive && setUnread(null));
    tick();
    const timer = setInterval(tick, 8000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [path, auditor]);

  return (
    <header className="nav">
      <a className="skip" href="#main">
        {t("skip")}
      </a>
      <div className="nav-top">
        <Link href="/" className="wordmark" aria-label={t("nav.home")}>
          <span className="wordmark-rule" aria-hidden />
          Ledger
        </Link>
        <div className="nav-user">
          <LanguageSwitch />
          <ThemeToggle />
          {user ? (
            <>
              <Link href="/account" className="who" title={t("nav.account")}>
                <Avatar name={user.name} />
                <span className="who-text">
                  <span className="who-name">{user.name}</span>
                  <span className={`who-role role-${user.role}`}>
                    {t(`role.${user.role}`)}
                    {user.requested_role ? ` · ${t("nav.pending")}` : ""}
                  </span>
                </span>
              </Link>
              <button
                className="icon-btn"
                title={t("nav.signout")}
                aria-label={t("nav.signout")}
                onClick={async () => {
                  await signOut();
                  router.push("/login");
                }}
              >
                <Icon name="out" />
              </button>
            </>
          ) : (
            !loading &&
            path !== "/login" && (
              <Link href="/login" className="btn btn-ghost btn-sm">
                {t("nav.signin")}
              </Link>
            )
          )}
        </div>
      </div>
      {user && (
        <nav className="nav-links" aria-label={t("nav.main")}>
          {LINKS.filter((l) => !l.roles || l.roles.includes(user.role)).map((l) => (
            <Link key={l.href} href={l.href} className={`nav-link${path?.startsWith(l.href) ? " is-active" : ""}`}>
              <Icon name={l.icon} size={17} />
              {t(l.label)}
              {l.href === "/audit" && unread !== null && unread > 0 && (
                <span className="bell" aria-label={t("nav.new_alerts", { n: unread })}>
                  {unread}
                </span>
              )}
              {l.href === "/users" && pending > 0 && (
                <span className="bell" aria-label={t("nav.waiting", { n: pending })}>
                  {pending}
                </span>
              )}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
