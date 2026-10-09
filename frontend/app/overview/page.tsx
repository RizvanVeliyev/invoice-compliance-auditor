"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Icon from "@/components/Icon";
import { api, money, Overview } from "@/lib/api";
import { Guard } from "@/lib/auth";
import { DICT } from "@/lib/dict";
import { useI18n } from "@/lib/i18n";

// Stack order keeps purple between green and red, so the two are never adjacent
// (the pair that red-green colour blindness confuses). Checked with the dataviz validator.
const SERIES = ["approved", "needs_review", "flagged"] as const;

function Daily({ days }: { days: Overview["by_day"] }) {
  const { t, day } = useI18n();
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const total = (d: Overview["by_day"][number]) => d.approved + d.needs_review + d.flagged;
  const max = Math.max(1, ...days.map(total));
  const any = days.some((d) => total(d) > 0);
  const label = (iso: string) => day(`${iso}T00:00:00`);

  return (
    <section className="sheet chart" aria-labelledby="daily">
      <div className="chart-head">
        <h2 id="daily" className="h-sub">
          {t("ov.daily", { n: days.length })}
        </h2>
        <button className="linkish" onClick={() => setTable((v) => !v)}>
          {t(table ? "ov.as_chart" : "ov.as_table")}
        </button>
      </div>
      <ul className="legend" aria-label={t("ov.legend")}>
        {SERIES.map((s) => (
          <li key={s}>
            <span className={`swatch seg-${s}`} aria-hidden /> {t(`status.${s}`)}
          </li>
        ))}
      </ul>

      {table ? (
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th>{t("ov.day")}</th>
                {SERIES.map((s) => (
                  <th key={s} className="num">
                    {t(`status.${s}`)}
                  </th>
                ))}
                <th className="num">{t("ov.total")}</th>
              </tr>
            </thead>
            <tbody>
              {days.map((d) => (
                <tr key={d.date}>
                  <td>{label(d.date)}</td>
                  {SERIES.map((s) => (
                    <td key={s} className="num fig">
                      {d[s]}
                    </td>
                  ))}
                  <td className="num fig">{total(d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !any ? (
        <p className="muted pad">{t("ov.no_period")}</p>
      ) : (
        <div className="cols" onMouseLeave={() => setHover(null)}>
          <span className="cols-max fig" aria-hidden>
            {max}
          </span>
          {days.map((d, i) => (
            <div
              key={d.date}
              className={`col${hover === i ? " is-hover" : ""}`}
              tabIndex={0}
              role="img"
              aria-label={`${label(d.date)}: ${SERIES.map((s) => `${t(`status.${s}`)} ${d[s]}`).join(", ")}`}
              onMouseEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            >
              <div className="col-stack">
                {[...SERIES].reverse().map(
                  (s) => d[s] > 0 && <span key={s} className={`seg seg-${s}`} style={{ height: `${(d[s] / max) * 100}%` }} />,
                )}
              </div>
              <span className="col-x">{i % 2 === (days.length - 1) % 2 ? label(d.date) : ""}</span>
              {hover === i && (
                <div className={`tip${i > days.length / 2 ? " tip-left" : ""}`} role="tooltip">
                  <strong>{label(d.date)}</strong>
                  {SERIES.map((s) => (
                    <span key={s} className="tip-row">
                      <span className={`swatch seg-${s}`} aria-hidden /> {t(`status.${s}`)}
                      <span className="fig">{d[s]}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function OverviewPage() {
  const { t, ago } = useI18n();
  const [o, setO] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    api<Overview>("/api/overview")
      .then((x) => {
        setO(x);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [load]);

  if (!o) {
    return (
      <div className="page">
        <h1>{t("nav.overview")}</h1>
        {failed ? (
          <p className="form-error" role="alert">
            {t("ov.error")}
          </p>
        ) : (
          <p className="muted">{t("ov.loading")}</p>
        )}
      </div>
    );
  }

  const cur = o.policy_currency;
  const c = o.counts;
  const rates = Object.entries(o.fx_rates);
  const ruleMax = Math.max(1, ...o.by_rule.map((r) => r.count));
  const hours = (h: number | null) =>
    h === null
      ? "—"
      : h < 1
        ? t("unit.min", { n: Math.max(1, Math.round(h * 60)) })
        : h < 48
          ? t("unit.h", { n: h.toFixed(1) })
          : t("unit.days", { n: (h / 24).toFixed(1) });
  // The server words a refused duplicate in English; show the matching sentence in the reader's language.
  const dupKey = (reason: string) =>
    reason.startsWith("it is the same file") ? "ov.dup_file" : reason.includes("invoice number") ? "ov.dup_number" : "ov.dup_amount";

  return (
    <div className="page">
      <header className="page-head head-row">
        <div>
          <h1>{t("nav.overview")}</h1>
          <p className="live">
            <span className="live-dot" aria-hidden /> {t("ov.live")}
          </p>
        </div>
        <div className="cta-row head-actions">
          <a href="/api/export.csv" className="btn btn-ghost" download>
            <Icon name="download" />
            {t("ov.csv")}
          </a>
          <Link href="/audit" className="btn btn-primary">
            <Icon name="inbox" />
            {t("home.cta_audit")}
            {c.in_review > 0 ? ` (${c.in_review})` : ""}
          </Link>
        </div>
      </header>

      {failed && (
        <p className="form-error" role="alert">
          {t("ov.error")}
        </p>
      )}

      <dl className="tiles">
        <div className="tile">
          <dt>{t("ov.t_submitted")}</dt>
          <dd className="fig">{c.total}</dd>
          <span className="tile-sub">{money(o.money.submitted, cur)}</span>
        </div>
        <div className="tile tile-review">
          <dt>{t("ov.t_waiting")}</dt>
          <dd className="fig">{c.in_review}</dd>
          <span className="tile-sub">{money(o.money.in_review, cur)}</span>
        </div>
        <div className="tile tile-ok">
          <dt>{t("ov.t_cleared")}</dt>
          <dd className="fig">{c.cleared}</dd>
          <span className="tile-sub">{t("ov.t_cleared_sub", { money: money(o.money.cleared, cur), n: c.auto_cleared })}</span>
        </div>
        <div className="tile tile-bad">
          <dt>{t("ov.t_rejected")}</dt>
          <dd className="fig">{c.rejected}</dd>
          <span className="tile-sub">{money(o.money.rejected, cur)}</span>
        </div>
        <div className="tile">
          <dt>{t("ov.t_dups")}</dt>
          <dd className="fig">{c.duplicates_blocked}</dd>
          <span className="tile-sub">{t("ov.t_dups_sub")}</span>
        </div>
        <div className="tile">
          <dt>{t("ov.t_time")}</dt>
          <dd className="fig">{hours(o.avg_decision_hours)}</dd>
          <span className="tile-sub">{t("ov.t_time_sub", { n: o.decisions })}</span>
        </div>
      </dl>
      <p className="hint">
        {t("ov.totals", { cur })}
        {rates.length > 0 && ` ${t("ov.rates", { rates: rates.map(([k, r]) => `1 ${k} = ${r} ${cur}`).join(", ") })}`}
        {o.unconverted > 0 && ` ${t("ov.unconverted", { n: o.unconverted })}`}
      </p>

      <Daily days={o.by_day} />

      <div className="ov-grid">
        <section className="sheet" aria-labelledby="rules">
          <h2 id="rules" className="h-sub">
            {t("ov.rules")}
          </h2>
          {o.by_rule.length === 0 ? (
            <p className="muted">{t("ov.no_rules")}</p>
          ) : (
            <ul className="bars">
              {o.by_rule.map((r) => {
                const text = `rule.${r.rule_id}` in DICT ? t(`rule.${r.rule_id}`) : r.description;
                return (
                  <li key={r.rule_id} title={text}>
                    <span className="bar-label">
                      <span className="rule-id">{r.rule_id}</span>
                      <span className="bar-desc">{text}</span>
                    </span>
                    <span className="bar-track">
                      <span className="bar-fill" style={{ width: `${(r.count / ruleMax) * 100}%` }} />
                      <span className="bar-n fig">{r.count}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="sheet" aria-labelledby="currencies">
          <h2 id="currencies" className="h-sub">
            {t("ov.by_currency")}
          </h2>
          {o.by_currency.length === 0 ? (
            <p className="muted">{t("ov.no_amounts")}</p>
          ) : (
            <div className="table-wrap">
              <table className="grid">
                <thead>
                  <tr>
                    <th>{t("ov.c_currency")}</th>
                    <th className="num">{t("ov.c_invoices")}</th>
                    <th className="num">{t("ov.c_as_invoiced")}</th>
                    <th className="num">{t("ov.c_in", { cur })}</th>
                  </tr>
                </thead>
                <tbody>
                  {o.by_currency.map((x) => (
                    <tr key={x.currency}>
                      <td>{x.currency}</td>
                      <td className="num fig">{x.count}</td>
                      <td className="num fig">{money(x.amount, x.currency)}</td>
                      <td className="num fig">{x.amount_policy > 0 ? money(x.amount_policy, cur) : t("ov.no_rate")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="sheet" aria-labelledby="people">
          <div className="chart-head">
            <h2 id="people" className="h-sub">
              {t("ov.by_employee")}
            </h2>
            <Link href="/employees" className="linkish">
              {t("ov.all_people")}
            </Link>
          </div>
          {o.by_employee.length === 0 ? (
            <p className="muted">{t("ov.no_employee")}</p>
          ) : (
            <div className="table-wrap">
              <table className="grid">
                <thead>
                  <tr>
                    <th>{t("role.employee")}</th>
                    <th className="num">{t("ov.c_invoices")}</th>
                    <th className="num">{t("status.flagged")}</th>
                    <th className="num">{t("ov.t_rejected")}</th>
                    <th className="num">{t("ov.c_total_in", { cur })}</th>
                  </tr>
                </thead>
                <tbody>
                  {o.by_employee.map((p) => (
                    <tr key={p.name}>
                      <td>{p.name}</td>
                      <td className="num fig">{p.count}</td>
                      <td className="num fig">{p.flagged}</td>
                      <td className="num fig">{p.rejected}</td>
                      <td className="num fig">{money(p.amount_policy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="sheet" aria-labelledby="decisions">
          <h2 id="decisions" className="h-sub">
            {t("ov.decisions")}
          </h2>
          {o.recent_decisions.length === 0 ? (
            <p className="muted">{t("ov.no_decisions")}</p>
          ) : (
            <>
              <ul className="blocks">
                {o.recent_decisions.map((d) => (
                  <li key={d.id}>
                    <span>
                      <span className={`tag tag-${d.decision}`}>{t(d.decision === "approved" ? "audit.cleared" : "stamp.rejected")}</span>{" "}
                      <Link href={`/audit?id=${d.id}`}>
                        #{d.id} {d.label}
                      </Link>
                      , {t("ov.from_by", { emp: d.employee_name })} <strong>{d.reviewer || t("common.an_auditor")}</strong>
                      {d.comment ? `: “${d.comment}”` : "."}
                    </span>
                    <span className="muted">{ago(d.decided_at)}</span>
                  </li>
                ))}
              </ul>
              <p className="hint by-auditor">
                {t("ov.per_auditor", { list: o.by_auditor.map((a) => `${a.name} ${a.count}`).join(", ") })}
              </p>
            </>
          )}
        </section>

        <section className="sheet" aria-labelledby="dupes">
          <h2 id="dupes" className="h-sub">
            {t("ov.dups")}
          </h2>
          {o.recent_blocks.length === 0 ? (
            <p className="muted">{t("ov.no_dups")}</p>
          ) : (
            <ul className="blocks">
              {o.recent_blocks.map((b) => (
                <li key={b.id}>
                  <span>
                    <strong>{b.user_name}</strong> {t("ov.dup_sent")} <span className="fig">{b.filename}</span>: {t(dupKey(b.reason))}{" "}
                    <Link href={`/audit?id=${b.original_id}`}>{t("ov.submission", { id: b.original_id })}</Link>.
                  </span>
                  <span className="muted">{ago(b.ts)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Guard roles={["auditor", "admin"]}>
      <OverviewPage />
    </Guard>
  );
}
