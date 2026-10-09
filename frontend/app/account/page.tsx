"use client";

import { useState } from "react";
import { Avatar } from "@/components/Icon";
import { useToast } from "@/components/Toasts";
import { postJson } from "@/lib/api";
import { Guard, useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

function Account() {
  const { user } = useAuth();
  const { t } = useI18n();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function change(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await postJson("/api/auth/password", { current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      toast({ title: t("acc.done"), body: t("acc.done_b"), tone: "approved" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("acc.error"));
    } finally {
      setBusy(false);
    }
  }

  if (!user) return null;
  return (
    <div className="page narrow">
      <div className="sheet signin">
        <div className="person-head">
          <Avatar name={user.name} size={56} />
          <div>
            <h1 className="h-name">{user.name}</h1>
            <p className="muted">
              {user.email} · {t(`role.${user.role}`)}
            </p>
          </div>
        </div>
        <form onSubmit={change} className="stack">
          <h3>{t("acc.change")}</h3>
          <label className="fld">
            <span>{t("acc.current")}</span>
            <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
          </label>
          <label className="fld">
            <span>{t("login.password_new")}</span>
            <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={8} required />
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="btn btn-primary" disabled={busy}>
            {t(busy ? "acc.saving" : "acc.btn")}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function AccountPage() {
  return (
    <Guard>
      <Account />
    </Guard>
  );
}
