"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";
import Pager, { usePaged } from "@/components/Pager";
import Report, { Timeline } from "@/components/Report";
import { api, fileUrl, moneyConverted, MySubmission, Outcome, SpendReport } from "@/lib/api";
import { Guard } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

const TAG: Record<Outcome, string> = { in_review: "needs_review", cleared: "approved", rejected: "rejected" };

function MyInvoices() {
  const { t, date } = useI18n();
  const [rows, setRows] = useState<MySubmission[] | null>(null);
  const [report, setReport] = useState<SpendReport | null>(null);
  const [months, setMonths] = useState(6);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const [show, setShow] = useState<Outcome | "all">("all");
  const [find, setFind] = useState("");

  const shown = useMemo(() => {
    const term = find.trim().toLowerCase();
    return (rows || []).filter(
      (r) =>
        (show === "all" || r.outcome === show) &&
        (!term || `${r.vendor} ${r.invoice_number} ${r.filename} #${r.id}`.toLowerCase().includes(term)),
    );
  }, [rows, show, find]);
  const paged = usePaged(shown, 8);
  const count = (o: Outcome) => (rows || []).filter((r) => r.outcome === o).length;

  const load = useCallback(() => {
    Promise.all([api<MySubmission[]>("/api/my/submissions"), api<SpendReport>(`/api/my/report?months=${months}`)])
      .then(([r, rep]) => {
        setRows(r);
        setReport(rep);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, [months]);

  // Decisions arrive while the page is open, so keep it current.
  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <div className="page">
      <header className="page-head head-row">
        <div>
          <h1>{t("nav.my")}</h1>
          <p className="lede">{t("my.lede")}</p>
        </div>
        <Link href="/submit" className="btn btn-primary">
          <Icon name="upload" />
          {t("nav.submit")}
        </Link>
      </header>

      {failed && (
        <p className="form-error" role="alert">
          {t("my.error")}
        </p>
      )}

      {rows && rows.length === 0 && (
        <div className="sheet sheet-empty">
          <p>{t("my.empty")}</p>
        </div>
      )}

      {rows && rows.length > 0 && report && (
        <>
          <h2 className="h-section">{t("rep.mine")}</h2>
          <Report r={report} months={months} onMonths={setMonths} />

          <h2 className="h-section">{t("audit.invoices")}</h2>
          <div className="filterbar">
            <div className="chips-filter" role="group" aria-label={t("filter.status")}>
              {(["all", "in_review", "cleared", "rejected"] as const).map((o) => (
                <button
                  key={o}
                  type="button"
                  className={`chip${show === o ? " is-on" : ""}`}
                  aria-pressed={show === o}
                  onClick={() => {
                    setShow(o);
                    paged.setPage(1);
                  }}
                >
                  {o === "all" ? t("filter.all") : t(`my.${o}`)}
                  <span className="fig">{o === "all" ? rows.length : count(o)}</span>
                </button>
              ))}
            </div>
            <div className="search" role="search">
              <span className="search-icon">
                <Icon name="search" />
              </span>
              <input
                type="search"
                aria-label={t("filter.invoices")}
                placeholder={t("filter.invoices")}
                value={find}
                onChange={(e) => {
                  setFind(e.target.value);
                  paged.setPage(1);
                }}
              />
            </div>
          </div>
          {shown.length === 0 && <p className="muted pad">{t("filter.none")}</p>}
          <ul className="mine">
            {paged.rows.map((r) => {
              const isOpen = open === r.id;
              return (
                <li key={r.id} className={`sheet mine-row mine-${r.outcome}`}>
                  <button className="mine-head" onClick={() => setOpen(isOpen ? null : r.id)} aria-expanded={isOpen}>
                    <span className="mine-main">
                      <span className="mine-vendor">{r.vendor || r.filename}</span>
                      <span className="mine-sub">
                        {t("my.sent", { id: r.id, date: date(r.ts) })}
                        {r.invoice_number ? `, ${t("my.invoice", { no: r.invoice_number })}` : ""}
                      </span>
                    </span>
                    <span className="mine-amt fig">{moneyConverted(r.amount, r.currency, r.conversion)}</span>
                    <span className={`tag tag-${TAG[r.outcome]}`}>{t(`my.${r.outcome}`)}</span>
                  </button>
                  {isOpen && (
                    <div className="mine-body">
                      <p>{t(`my.m_${r.outcome}`)}</p>
                      {r.violations.length > 0 && (
                        <ol className="findings">
                          {r.violations.map((v) => (
                            <li key={v.rule_id} className={`finding sev-${v.severity}`}>
                              <span className="rule-id">{v.rule_id}</span>
                              <p>{v.explanation}</p>
                            </li>
                          ))}
                        </ol>
                      )}
                      {r.review_reasons.length > 0 && (
                        <ul className="reasons">
                          {r.review_reasons.map((x, i) => (
                            <li key={i}>{x}</li>
                          ))}
                        </ul>
                      )}
                      <h3>{t("audit.history")}</h3>
                      <Timeline events={r.events} />
                      <a className="linkish" href={fileUrl(r.id)} target="_blank" rel="noreferrer">
                        {t("my.open_file", { file: r.filename })}
                      </a>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          <Pager {...paged} onPage={paged.setPage} />
        </>
      )}
    </div>
  );
}

export default function MyPage() {
  return (
    <Guard>
      <MyInvoices />
    </Guard>
  );
}
