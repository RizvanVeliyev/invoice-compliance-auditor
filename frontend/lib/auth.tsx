"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, AuthState, Role, SIGNED_OUT_EVENT, User } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Ctx = {
  user: User | null;
  loading: boolean;
  setupRequired: boolean;
  setUser: (u: User | null) => void;
  signOut: () => Promise<void>;
};

const AuthCtx = createContext<Ctx>({
  user: null,
  loading: true,
  setupRequired: false,
  setUser: () => {},
  signOut: async () => {},
});

export function useAuth() {
  return useContext(AuthCtx);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [setupRequired, setSetupRequired] = useState(false);

  useEffect(() => {
    api<AuthState>("/api/auth/state")
      .then((s) => {
        setUserState(s.user);
        setSetupRequired(s.setup_required);
      })
      .catch(() => setUserState(null))
      .finally(() => setLoading(false));
    // Any request that comes back 401 means the session ended (expired, or an admin changed the account).
    const gone = () => setUserState(null);
    window.addEventListener(SIGNED_OUT_EVENT, gone);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, gone);
  }, []);

  // While an auditor request is pending, look again now and then so the approval shows up without a reload.
  const waiting = !!user?.requested_role;
  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(() => {
      api<AuthState>("/api/auth/state")
        .then((s) => setUserState(s.user))
        .catch(() => {});
    }, 8000);
    return () => clearInterval(t);
  }, [waiting]);

  const setUser = useCallback((u: User | null) => {
    setUserState(u);
    if (u?.role === "admin") setSetupRequired(false);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setUserState(null);
    }
  }, []);

  return <AuthCtx.Provider value={{ user, loading, setupRequired, setUser, signOut }}>{children}</AuthCtx.Provider>;
}

/** Shows its children only to a signed-in person with one of `roles`; everyone else is sent to sign in. */
export function Guard({ roles, children }: { roles?: Role[]; children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(path || "/")}`);
  }, [loading, user, router, path]);

  if (loading || !user) {
    return (
      <div className="page narrow">
        <p className="muted">{t("common.checking")}</p>
      </div>
    );
  }
  if (roles && !roles.includes(user.role)) {
    const waiting = user.requested_role && roles.includes(user.requested_role);
    return (
      <div className="page narrow">
        <div className="sheet">
          <h1>{t(waiting ? "guard.wait_title" : "guard.no_title")}</h1>
          <p className="lede">
            {waiting ? t("guard.wait_body") : t("guard.no_body", { name: user.name, role: t(`role.${user.role}`) })}
          </p>
          <div className="cta-row">
            <Link href="/submit" className="btn btn-primary">
              {t("nav.submit")}
            </Link>
            <Link href="/my" className="btn btn-ghost">
              {t("nav.my")}
            </Link>
          </div>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
