"use client";

import { useState } from "react";
import { money, SpendReport } from "@/lib/api";
import { DICT } from "@/lib/dict";
import { useI18n } from "@/lib/i18n";

/** Spending for one person: totals, a bar per month, and where the money went. Amounts are in the policy currency. */
export default function Report({
  r,
  months,
  onMonths,
}: {
  r: SpendReport;
  months: number;
  onMonths: (n: number) => void;
}) {
  const { t, month: monthName } = useI18n();
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const cur = r.policy_currency;
  const max = Math.max(1, ...r.months.map((m) => m.amount));
  const catMax = Math.max(1, ...r.by_category.map((c) => c.amount));
  const short = (n: number) => (n >= 10000 ? `${Math.round(n / 1000)}k` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(Math.round(n)));
  const category = (c: string) => (`cat.${c}` in DICT ? t(`cat.${c}`) : c);

  return (
    <div className="report">
      <dl className="tiles">
        <div className="tile">
          <dt>{t("rep.total")}</dt>
          <dd className="fig">{money(r.money.amount)}</dd>
          <span className="tile-sub">
            {cur} · {t("rep.invoices", { n: r.totals.count })}
          </span>
        </div>
        <div className="tile tile-ok">
          <dt>{t("rep.cleared")}</dt>
          <dd className="fig">{money(r.money.cleared)}</dd>
          <span className="tile-sub">
            {cur} · {t("rep.invoices", { n: r.totals.cleared })}
          </span>
        </div>
        <div className="tile tile-review">
          <dt>{t("rep.waiting")}</dt>
          <dd className="fig">{money(r.money.in_review)}</dd>
          <span className="tile-sub">
            {cur} · {t("rep.invoices", { n: r.totals.in_review })}
          </span>
        </div>
        <div className="tile tile-bad">
          <dt>{t("rep.rejected")}</dt>
          <dd className="fig">{money(r.money.rejected)}</dd>
          <span className="tile-sub">
            {cur} · {t("rep.invoices", { n: r.totals.rejected })}
          </span>
        </div>
      </dl>

      <div className="report-grid">
        <section className="sheet" aria-labelledby="rep-monthly">
          <div className="chart-head">
            <h2 id="rep-monthly" className="h-sub">
              {t("rep.monthly", { cur })}
            </h2>
            <span className="chart-tools">
              <span className="seg-switch" role="group" aria-label={t("rep.period")}>
                {[6, 12].map((n) => (
                  <button key={n} type="button" className={months === n ? "is-on" : ""} aria-pressed={months === n} onClick={() => onMonths(n)}>
                    {t(n === 6 ? "rep.m6" : "rep.m12")}
                  </button>
                ))}
              </span>
              <button className="linkish" onClick={() => setTable((v) => !v)}>
                {t(table ? "ov.as_chart" : "ov.as_table")}
              </button>
            </span>
          </div>
          {table ? (
            <div className="table-wrap">
              <table className="grid">
                <thead>
                  <tr>
                    <th>{t("rep.c_month")}</th>
                    <th className="num">{t("ov.c_invoices")}</th>
                    <th className="num">{t("rep.c_amount", { cur })}</th>
                  </tr>
                </thead>
                <tbody>
                  {r.months.map((m) => (
                    <tr key={m.month}>
                      <td>{monthName(m.month, true)}</td>
                      <td className="num fig">{m.count}</td>
                      <td className="num fig">{money(m.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : r.totals.count === 0 ? (
            <p className="muted pad">{t("rep.none")}</p>
          ) : (
            <div className="mcols" onMouseLeave={() => setHover(null)}>
              {r.months.map((m, i) => (
                <div
                  key={m.month}
                  className={`mcol${hover === i ? " is-hover" : ""}`}
                  tabIndex={0}
                  role="img"
                  aria-label={`${monthName(m.month, true)}: ${money(m.amount, cur)}, ${t("rep.invoices", { n: m.count })}`}
                  onMouseEnter={() => setHover(i)}
                  onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                >
                  <div className="mcol-bar">
                    {m.amount > 0 && <span className="mcol-val fig">{short(m.amount)}</span>}
                    {m.amount > 0 && <span className="mcol-fill" style={{ height: `${(m.amount / max) * 82}%` }} />}
                  </div>
                  <span className="col-x">{monthName(m.month)}</span>
                  {hover === i && (
                    <div className={`tip${i > r.months.length / 2 ? " tip-left" : ""}`} role="tooltip">
                      <strong>{monthName(m.month, true)}</strong>
                      <span className="tip-row">
                        {t("rep.total")} <span className="fig">{money(m.amount, cur)}</span>
                      </span>
                      <span className="tip-row">
                        {t("rep.cleared")} <span className="fig">{money(m.cleared)}</span>
                      </span>
                      <span className="tip-row">
                        {t("rep.waiting")} <span className="fig">{money(m.in_review)}</span>
                      </span>
                      <span className="tip-row">
                        {t("rep.rejected")} <span className="fig">{money(m.rejected)}</span>
                      </span>
                      <span className="tip-row">{t("rep.invoices", { n: m.count })}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <div className="stack-lg">
          <section className="sheet" aria-labelledby="rep-cat">
            <h2 id="rep-cat" className="h-sub">
              {t("rep.by_category")}
            </h2>
            {r.by_category.length === 0 ? (
              <p className="muted">{t("rep.none")}</p>
            ) : (
              <ul className="bars">
                {r.by_category.map((c) => (
                  <li key={c.category}>
                    <span className="bar-label">
                      <span className="bar-name">{category(c.category)}</span>
                      <span className="bar-desc">{t("rep.invoices", { n: c.count })}</span>
                    </span>
                    <span className="bar-track">
                      <span className="bar-fill" style={{ width: `${(c.amount / catMax) * 100}%` }} />
                      <span className="bar-n fig">{money(c.amount)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          {r.top_vendors.length > 0 && (
            <section className="sheet" aria-labelledby="rep-vendors">
              <h2 id="rep-vendors" className="h-sub">
                {t("rep.vendors")}
              </h2>
              <div className="table-wrap">
                <table className="grid">
                  <tbody>
                    {r.top_vendors.map((v) => (
                      <tr key={v.vendor}>
                        <td>{v.vendor}</td>
                        <td className="num fig">{v.count}</td>
                        <td className="num fig">{money(v.amount, cur)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

/** A submission's history: who did what, when. Internal notes only reach this list for the audit team. */
export function Timeline({ events }: { events: { id: number; ts: string; user_name: string; kind: string; text: string }[] }) {
  const { t, dateTime } = useI18n();
  return (
    <ol className="timeline">
      {events.map((e) => (
        <li key={e.id} className={`ev-${e.kind}`}>
          <strong>{e.user_name}</strong> {t(`ev.${e.kind}`)}
          <span className="ev-when">{dateTime(e.ts)}</span>
          {e.text && <p className="ev-text">{e.text}</p>}
        </li>
      ))}
    </ol>
  );
}
