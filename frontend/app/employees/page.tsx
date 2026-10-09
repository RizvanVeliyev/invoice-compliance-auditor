"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Icon, { Avatar } from "@/components/Icon";
import Pager, { usePaged } from "@/components/Pager";
import Report from "@/components/Report";
import { api, money, Person, PersonDetail } from "@/lib/api";
import { Guard } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

function Employees() {
  const { t, date } = useI18n();
  const [people, setPeople] = useState<Person[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<PersonDetail | null>(null);
  const [months, setMonths] = useState(6);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const id = Number(new URLSearchParams(window.location.search).get("id"));
    if (id) setSelected(id);
    const load = () =>
      api<Person[]>("/api/employees")
        .then((p) => {
          setPeople(p);
          setFailed(false);
        })
        .catch(() => setFailed(true));
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (selected === null) return;
    let alive = true;
    api<PersonDetail>(`/api/employees/${selected}?months=${months}`)
      .then((d) => alive && setDetail(d))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [selected, months]);

  const cur = detail?.report.policy_currency || "AZN";
  const [find, setFind] = useState("");
  const [role, setRole] = useState("");
  const shown = useMemo(() => {
    const term = find.trim().toLowerCase();
    return (people || []).filter(
      (p) =>
        (!term || `${p.name} ${p.email}`.toLowerCase().includes(term)) &&
        (!role || (role === "with" ? p.count > 0 : p.role === role)),
    );
  }, [people, find, role]);
  const list = usePaged(shown, 10);
  const invoices = usePaged(detail?.submissions || [], 8);

  return (
    <div className="page">
      <header className="page-head">
        <h1>{t("nav.employees")}</h1>
        <p className="lede">{t("emp.lede")}</p>
      </header>

      {failed && (
        <p className="form-error" role="alert">
          {t("emp.error")}
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
              list.setPage(1);
            }}
          />
        </div>
        <label className="fsel">
          {t("filter.role")}
          <select
            value={role}
            onChange={(e) => {
              setRole(e.target.value);
              list.setPage(1);
            }}
          >
            <option value="">{t("filter.all")}</option>
            <option value="employee">{t("role.employee")}</option>
            <option value="auditor">{t("role.auditor")}</option>
            <option value="with">{t("filter.with_invoices")}</option>
          </select>
        </label>
      </div>

      <div className="people-grid">
        <div className="people-wrap">
        <ul className="people" aria-label={t("nav.employees")}>
          {!people && !failed && <li className="queue-empty">{t("emp.loading")}</li>}
          {people && shown.length === 0 && <li className="queue-empty">{t("filter.none")}</li>}
          {list.rows.map((p) => (
            <li key={p.id}>
              <button className={`person${selected === p.id ? " is-sel" : ""}`} onClick={() => setSelected(p.id)} aria-current={selected === p.id}>
                <span className="person-main">
                  <Avatar name={p.name} size={30} />
                  <span className="person-name">
                    {p.name}
                    <span className={`who-role role-${p.role}`}>{t(`role.${p.role}`)}</span>
                  </span>
                </span>
                <span className="person-amt fig">{money(p.amount, "AZN")}</span>
                <span className="person-sub">
                  {t("rep.invoices", { n: p.count })}
                  {p.flagged > 0 ? ` · ${t("status.flagged")}: ${p.flagged}` : ""}
                  {p.in_review > 0 ? ` · ${t("emp.c_waiting")}: ${p.in_review}` : ""}
                  {p.last_submission ? ` · ${date(p.last_submission)}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <Pager {...list} onPage={list.setPage} />
        </div>

        <div>
          {!detail && (
            <div className="sheet detail-empty">
              <p>{t("emp.pick")}</p>
            </div>
          )}
          {detail && (
            <div className="stack-lg">
              <div className="person-head">
                <Avatar name={detail.user.name} size={52} />
                <div>
                  <h2>{detail.user.name}</h2>
                  <p className="muted">
                    {detail.user.email} · {t(`role.${detail.user.role}`)}
                    {!detail.user.active ? ` · ${t("users.deactivated")}` : ""}
                  </p>
                </div>
              </div>
              <Report r={detail.report} months={months} onMonths={setMonths} />
              <section className="sheet" aria-labelledby="their">
                <h2 id="their" className="h-sub">
                  {t("emp.their")}
                </h2>
                {detail.submissions.length === 0 ? (
                  <p className="muted">{t("emp.none")}</p>
                ) : (
                  <div className="table-wrap">
                    <table className="grid">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>{t("f.vendor")}</th>
                          <th>{t("f.date")}</th>
                          <th className="num">{t("f.amount")}</th>
                          <th>{t("audit.decision")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {invoices.rows.map((s) => (
                          <tr key={s.id}>
                            <td className="fig">
                              <Link href={`/audit?id=${s.id}`}>#{s.id}</Link>
                            </td>
                            <td>{s.vendor || s.filename}</td>
                            <td>{date(s.ts)}</td>
                            <td className="num fig">{s.amount === null ? "—" : money(s.amount, s.currency)}</td>
                            <td>
                              {s.decision ? (
                                <span className={`tag tag-${s.decision}`}>{t(s.decision === "approved" ? "audit.cleared" : "stamp.rejected")}</span>
                              ) : (
                                <span className={`tag tag-${s.status}`}>{t(`status.${s.status}`)}</span>
                              )}{" "}
                              {s.violation_ids.map((v) => (
                                <span key={v} className="tag tag-rule fig">
                                  {v}
                                </span>
                              ))}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <Pager {...invoices} onPage={invoices.setPage} />
              </section>
              <p className="hint">
                {t("ov.totals", { cur })}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function EmployeesPage() {
  return (
    <Guard roles={["auditor", "admin"]}>
      <Employees />
    </Guard>
  );
}
