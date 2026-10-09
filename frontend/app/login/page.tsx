"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, isAuditor, postJson, User } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import Icon from "@/components/Icon";
import { LogoMark } from "@/components/Logo";
import { useI18n } from "@/lib/i18n";

type Mode = "signin" | "register" | "setup";
type Side = "employee" | "auditor";
const SIDES: Side[] = ["employee", "auditor"];

/** Where to go after signing in: the page that sent you here, or the natural home for your role. */
function destination(u: User) {
  const next = new URLSearchParams(window.location.search).get("next");
  if (next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login")) return next;
  return isAuditor(u) ? "/audit" : "/submit";
}

export default function Login() {
  const router = useRouter();
  const { t } = useI18n();
  const { user, loading, setupRequired, setUser } = useAuth();
  const [mode, setMode] = useState<Mode>("signin");
  const [side, setSide] = useState<Side>("employee");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsApproval, setNeedsApproval] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace(destination(user));
  }, [loading, user, router]);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("register") !== null) setMode("register");
    if (q.get("side") === "auditor") setSide("auditor");
    api<{ auditor_signup?: string }>("/api/health")
      .then((h) => setNeedsApproval(h.auditor_signup === "approval"))
      .catch(() => {});
  }, []);

  function go(m: Mode) {
    setMode(m);
    setError(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u =
        mode === "signin"
          ? await postJson<User>("/api/auth/login", { email, password, side })
          : mode === "register"
            ? await postJson<User>("/api/auth/register", { name, email, password, role: side })
            : await postJson<User>("/api/auth/setup", { name, email, password });
      setUser(u);
      router.replace(destination(u));
    } catch (err) {
      // 403 on sign-in: the password was right, but this account belongs to the other side.
      if (mode === "signin" && err instanceof ApiError && err.status === 403) {
        setError(
          err.message.includes("not approved") ? t("login.side_pending") : t(side === "auditor" ? "login.side_not_auditor" : "login.side_not_employee"),
        );
      } else {
        setError(err instanceof Error ? err.message : t("login.failed"));
      }
      setBusy(false);
    }
  }

  if (loading || user) {
    return (
      <div className="page narrow">
        <p className="muted">{t("common.checking")}</p>
      </div>
    );
  }

  const creating = mode !== "signin";
  const title = mode === "setup" ? t("login.setup_title") : t(`login.${mode}_${side}`);

  return (
    <div className="page narrow">
      <form className="sheet signin" onSubmit={submit}>
        <div className="signin-mark">
          <LogoMark size={44} />
        </div>
        {mode !== "setup" && (
          <div className="sides" role="tablist" aria-label={t("login.sides")}>
            {SIDES.map((s) => (
              <button
                key={s}
                type="button"
                role="tab"
                aria-selected={side === s}
                className={`side${side === s ? " is-on" : ""}`}
                onClick={() => {
                  setSide(s);
                  setError(null);
                }}
              >
                {t(`login.side_${s}`)}
              </button>
            ))}
          </div>
        )}

        <h1>{title}</h1>
        <p>{mode === "setup" ? t("login.setup_body") : t(`login.does_${side}`)}</p>
        {mode === "register" && side === "auditor" && needsApproval && (
          <p className="notice">{t("login.approval_notice")}</p>
        )}

        {creating && (
          <label className="fld">
            <span>{t("login.name")}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
          </label>
        )}
        <label className="fld">
          <span>{t("login.email")}</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
        </label>
        <label className="fld">
          <span>{t(creating ? "login.password_new" : "login.password")}</span>
          <span className="pw">
            <input
              type={reveal ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={creating ? "new-password" : "current-password"}
              minLength={creating ? 8 : undefined}
              required
            />
            <button
              type="button"
              className="pw-eye"
              onClick={() => setReveal((v) => !v)}
              aria-pressed={reveal}
              aria-label={t(reveal ? "login.hide_pw" : "login.show_pw")}
              title={t(reveal ? "login.hide_pw" : "login.show_pw")}
            >
              <Icon name={reveal ? "eye-off" : "eye"} />
            </button>
          </span>
        </label>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button className="btn btn-primary btn-wide" disabled={busy}>
          {busy
            ? t("login.busy")
            : t(mode === "signin" ? "login.btn_signin" : mode === "setup" ? "login.btn_setup" : "login.btn_register")}
        </button>

        <p className="signin-foot">
          {mode === "signin" ? (
            <>
              {t("login.no_account")}{" "}
              <button type="button" className="linkish" onClick={() => go("register")}>
                {t(`login.register_${side}`)}
              </button>
              . {t("login.admin_hint")}
            </>
          ) : (
            <>
              {t("login.already")}{" "}
              <button type="button" className="linkish" onClick={() => go("signin")}>
                {t("login.btn_signin")}
              </button>
            </>
          )}
        </p>
        {setupRequired && mode !== "setup" && (
          <p className="signin-foot">
            {t("login.no_admin")}{" "}
            <button type="button" className="linkish" onClick={() => go("setup")}>
              {t("login.setup_link")}
            </button>
          </p>
        )}
      </form>
    </div>
  );
}
