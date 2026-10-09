"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Icon, { Avatar } from "@/components/Icon";
import Pager, { usePaged } from "@/components/Pager";
import { useToast } from "@/components/Toasts";
import { api, postJson, Role, User } from "@/lib/api";
import { Guard, useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

// There is one admin account (yours); everyone else is an employee or an auditor.
const ROLES: Role[] = ["employee", "auditor"];

function Accounts() {
  const { user: me } = useAuth();
  const { t, ago, dateTime } = useI18n();
  const toast = useToast();
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", email: "", role: "employee" as Role, password: "" });
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resetting, setResetting] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const load = useCallback(() => {
    api<User[]>("/api/users")
      .then(setUsers)
      .catch((e) => setError(e instanceof Error ? e.message : t("users.e_load")));
  }, [t]);

  // New registrations and auditor requests arrive while the page is open.
  useEffect(() => {
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      const u = await postJson<User>("/api/users", form);
      toast({ title: t("users.t_created", { name: u.name }), body: t("users.t_created_b", { email: u.email }), tone: "approved" });
      setForm({ name: "", email: "", role: "employee", password: "" });
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t("users.e_create"));
    } finally {
      setBusy(false);
    }
  }

  async function patch(
    u: User,
    body: Partial<{ role: Role; active: boolean; password: string; decline_request: boolean }>,
    done: string,
  ) {
    setError(null);
    try {
      await postJson<User>(`/api/users/${u.id}`, body, "PATCH");
      toast({ title: done, tone: "info" });
      setResetting(null);
      setNewPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("users.e_save"));
    }
    load();
  }

  const waiting = (users || []).filter((u) => u.requested_role && u.active);
  const [find, setFind] = useState("");
  const [kind, setKind] = useState("");
  const shown = useMemo(() => {
    const term = find.trim().toLowerCase();
    return (users || []).filter(
      (u) =>
        (!term || `${u.name} ${u.email}`.toLowerCase().includes(term)) &&
        (!kind || (kind === "active" ? u.active : kind === "inactive" ? !u.active : u.role === kind)),
    );
  }, [users, find, kind]);
  const paged = usePaged(shown, 10);

  return (
    <div className="page">
      <header className="page-head">
        <h1>{t("nav.accounts")}</h1>
        <p className="lede">{t("users.lede")}</p>
      </header>

      {waiting.length > 0 && (
        <section className="sheet requests" aria-labelledby="requests">
          <h2 id="requests" className="h-sub">
            {t("users.waiting", { n: waiting.length })}
          </h2>
          <p className="muted">{t("users.waiting_p")}</p>
          <ul>
            {waiting.map((u) => (
              <li key={u.id}>
                <span className="u-cell">
                  <Avatar name={u.name} />
                  <span>
                    <span className="u-name">{u.name}</span>
                    <span className="u-email">
                      {u.email}, {t("users.registered", { ago: ago(u.created_at) })}
                    </span>
                  </span>
                </span>
                <span className="req-actions">
                  <button className="btn btn-ok btn-sm" onClick={() => patch(u, { role: "auditor" }, t("users.t_approved", { name: u.name }))}>
                    <Icon name="check" size={16} />
                    {t("users.approve")}
                  </button>
                  <button className="btn btn-bad btn-sm" onClick={() => patch(u, { decline_request: true }, t("users.t_declined", { name: u.name }))}>
                    {t("users.decline")}
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="users-grid">
        <section aria-labelledby="people">
          <h2 id="people" className="h-sub">
            {t("users.people", { n: users ? users.filter((u) => u.active).length : 0 })}
          </h2>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="filterbar">
            <div className="search" role="search">
              <span className="search-icon">
                <Icon name="search" />
              </span>
              <input
                type="search"
                aria-label={t("filter.people")}
                placeholder={t("filter.people")}
                value={find}
                onChange={(e) => {
                  setFind(e.target.value);
                  paged.setPage(1);
                }}
              />
            </div>
            <label className="fsel">
              {t("filter.role")}
              <select
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  paged.setPage(1);
                }}
              >
                <option value="">{t("filter.all")}</option>
                <option value="employee">{t("role.employee")}</option>
                <option value="auditor">{t("role.auditor")}</option>
                <option value="admin">{t("role.admin")}</option>
                <option value="active">{t("filter.active")}</option>
                <option value="inactive">{t("filter.inactive")}</option>
              </select>
            </label>
          </div>
          <div className="sheet table-wrap">
            <table className="grid">
              <thead>
                <tr>
                  <th>{t("users.c_name")}</th>
                  <th>{t("users.c_role")}</th>
                  <th>{t("users.c_last")}</th>
                  <th>
                    <span className="sr-only">{t("users.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {paged.rows.map((u) => {
                  const self = u.id === me?.id;
                  return (
                    <tr key={u.id} className={u.active ? undefined : "is-off"}>
                      <td>
                        <span className="u-cell">
                          <Avatar name={u.name} />
                          <span>
                            <span className="u-name">
                              {u.name}
                              {self && <span className="muted"> {t("users.you")}</span>}
                            </span>
                            <span className="u-email">{u.email}</span>
                          </span>
                        </span>
                      </td>
                      <td>
                        {u.role === "admin" ? (
                          <span className="role role-admin">{t("role.admin")}</span>
                        ) : (
                          <select
                            aria-label={t("users.role_of", { name: u.name })}
                            value={u.role}
                            disabled={!u.active}
                            onChange={(e) =>
                              patch(u, { role: e.target.value as Role }, t("users.t_role", { name: u.name, role: t(`role.${e.target.value}`) }))
                            }
                          >
                            {ROLES.map((r) => (
                              <option key={r} value={r}>
                                {t(`role.${r}`)}
                              </option>
                            ))}
                          </select>
                        )}
                      </td>
                      <td className="muted">{!u.active ? t("users.deactivated") : u.last_login ? dateTime(u.last_login) : t("users.never")}</td>
                      <td className="u-actions">
                        {resetting === u.id ? (
                          <form
                            className="inline-form"
                            onSubmit={(e) => {
                              e.preventDefault();
                              patch(u, { password: newPassword }, t("users.t_pw", { name: u.name }));
                            }}
                          >
                            <input
                              type="text"
                              aria-label={t("users.new_pw")}
                              placeholder={t("users.new_pw")}
                              value={newPassword}
                              minLength={8}
                              autoFocus
                              onChange={(e) => setNewPassword(e.target.value)}
                            />
                            <button className="btn btn-primary btn-sm" disabled={newPassword.length < 8}>
                              {t("users.set")}
                            </button>
                            <button type="button" className="linkish" onClick={() => setResetting(null)}>
                              {t("common.cancel")}
                            </button>
                          </form>
                        ) : (
                          <>
                            <button
                              className="linkish"
                              onClick={() => {
                                setResetting(u.id);
                                setNewPassword("");
                              }}
                            >
                              {t("users.set_pw")}
                            </button>
                            {!self && u.role !== "admin" && (
                              <button
                                className="linkish"
                                onClick={() => patch(u, { active: !u.active }, t(u.active ? "users.t_off" : "users.t_on", { name: u.name }))}
                              >
                                {t(u.active ? "users.deactivate" : "users.reactivate")}
                              </button>
                            )}
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!users && !error && <p className="muted pad">{t("users.loading")}</p>}
            {users && shown.length === 0 && <p className="muted pad">{t("filter.none")}</p>}
            <Pager {...paged} onPage={paged.setPage} />
          </div>
          <p className="hint">{t("users.hint")}</p>
        </section>

        <form className="sheet stack" onSubmit={create} aria-labelledby="add">
          <h2 id="add" className="h-sub">
            {t("users.add")}
          </h2>
          <label className="fld">
            <span>{t("login.name")}</span>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label className="fld">
            <span>{t("login.email")}</span>
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="off" required />
          </label>
          <label className="fld">
            <span>{t("users.c_role")}</span>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`role.${r}`)}: {t(`users.h_${r}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="fld">
            <span>{t("users.first_pw")}</span>
            <input
              type="text"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              autoComplete="off"
              minLength={8}
              required
            />
          </label>
          {formError && (
            <p className="form-error" role="alert">
              {formError}
            </p>
          )}
          <button className="btn btn-primary" disabled={busy}>
            <Icon name="plus" />
            {t(busy ? "users.creating" : "users.create")}
          </button>
          <p className="hint">{t("users.change_hint")}</p>
        </form>
      </div>
    </div>
  );
}

export default function UsersPage() {
  return (
    <Guard roles={["admin"]}>
      <Accounts />
    </Guard>
  );
}
