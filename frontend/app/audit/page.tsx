"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import Icon, { Avatar } from "@/components/Icon";
import Pager from "@/components/Pager";
import { Timeline } from "@/components/Report";
import ResultView from "@/components/ResultView";
import Stamp from "@/components/Stamp";
import { useToast } from "@/components/Toasts";
import { AlertSummary, api, apiPage, fileUrl, money, moneyConverted, postJson, SubmissionDetail, SubmissionRow } from "@/lib/api";
import { Guard, useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

type Filter = "open" | "flagged" | "needs_review" | "decided" | "all";
const FILTERS: { id: Filter; label: string; count?: keyof AlertSummary }[] = [
  { id: "open", label: "audit.f_open", count: "open" },
  { id: "flagged", label: "status.flagged", count: "flagged" },
  { id: "needs_review", label: "status.needs_review", count: "needs_review" },
  { id: "decided", label: "audit.f_decided", count: "decided" },
  { id: "all", label: "audit.f_all", count: "total" },
];
const POLL_MS = 5000;

const PAGE_SIZE = 12;
type Extra = { currency: string; from: string; to: string };
const NO_EXTRA: Extra = { currency: "", from: "", to: "" };

function query(f: Filter, search: string, x: Extra, page: number) {
  const p = new URLSearchParams();
  if (f === "open") p.set("state", "open");
  if (f === "decided") p.set("state", "decided");
  if (f === "flagged" || f === "needs_review") {
    p.set("status", f);
    p.set("state", "open");
  }
  if (search.trim()) p.set("q", search.trim());
  if (x.currency) p.set("currency", x.currency);
  if (x.from) p.set("date_from", x.from);
  if (x.to) p.set("date_to", x.to);
  p.set("page", String(page));
  p.set("page_size", String(PAGE_SIZE));
  return `?${p.toString()}`;
}

function AuditDesk() {
  const toast = useToast();
  const { t, ago } = useI18n();
  const [filter, setFilter] = useState<Filter>("open");
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [extra, setExtra] = useState<Extra>(NO_EXTRA);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [currencies, setCurrencies] = useState<string[]>(["AZN"]);
  const [rows, setRows] = useState<SubmissionRow[]>([]);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notifyOn, setNotifyOn] = useState(false);
  const latest = useRef<number | null>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  // Search as the auditor types, a moment after they stop.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(typed), 250);
    return () => clearTimeout(timer);
  }, [typed]);

  // Any change to what is being looked for starts again from the first page.
  useEffect(() => {
    setPage(1);
  }, [filter, search, extra]);

  useEffect(() => {
    api<{ accepted_currencies?: string[]; currency: string }>("/api/policy")
      .then((p) => setCurrencies(p.accepted_currencies || [p.currency]))
      .catch(() => {});
  }, []);

  const filtering = !!(extra.currency || extra.from || extra.to);

  const amount = useCallback(
    (r: SubmissionRow) => (r.amount === null ? t("common.unreadable") : money(r.amount, r.currency)),
    [t],
  );

  const handle = useCallback(
    (e: unknown) => {
      setLoadError(e instanceof Error ? e.message : t("common.error"));
    },
    [t],
  );

  const refresh = useCallback(async () => {
    try {
      const [s, list] = await Promise.all([
        api<AlertSummary>("/api/alerts/summary"),
        apiPage<SubmissionRow>(`/api/submissions${query(filter, search, extra, page)}`),
      ]);
      setLoadError(null);
      setSummary(s);
      setRows(list.rows);
      setTotal(list.total);
      // The list got shorter (a decision moved an invoice out of this view): step back to the last page.
      if (list.rows.length === 0 && list.total > 0 && page > 1) setPage(Math.ceil(list.total / PAGE_SIZE));
      // New submissions since the last poll: highlight them and raise an alert.
      if (latest.current !== null && s.latest_id > latest.current) {
        const all = await api<SubmissionRow[]>("/api/submissions?limit=20");
        const news = all.filter((r) => r.id > (latest.current as number));
        setFresh((prev) => new Set([...Array.from(prev), ...news.map((n) => n.id)]));
        news
          .filter((n) => n.alert)
          .reverse()
          .forEach((n) => {
            const title = t("audit.toast", { status: t(`status.${n.status}`), name: n.employee_name });
            const body = `${n.vendor || t("common.unknown_vendor")}, ${amount(n)}`;
            toast({ title, body, tone: n.status, href: `/audit?id=${n.id}` });
            try {
              if (notifyOn && document.hidden && Notification.permission === "granted") {
                new Notification(`PhysicalAI: ${title}`, { body });
              }
            } catch {
              /* notifications unsupported */
            }
          });
      }
      latest.current = s.latest_id;
      document.title = s.unread > 0 ? `(${s.unread}) ${t("audit.tab")}` : t("audit.tab");
    } catch (e) {
      handle(e);
    }
  }, [filter, search, extra, page, handle, toast, notifyOn, t, amount]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    const id = Number(new URLSearchParams(window.location.search).get("id"));
    if (id) {
      setSelected(id);
      setFilter("all"); // a linked invoice may already be decided, so show the list that contains it
    }
    try {
      setNotifyOn(typeof Notification !== "undefined" && Notification.permission === "granted");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (selected === null) {
      setDetail(null);
      return;
    }
    let alive = true;
    api<SubmissionDetail>(`/api/submissions/${selected}`)
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        setRows((rs) => rs.map((r) => (r.id === d.id && r.review_state === "new" ? { ...r, review_state: "seen" } : r)));
        if (window.innerWidth < 1000) detailRef.current?.scrollIntoView({ behavior: "smooth" });
      })
      .catch(handle);
    return () => {
      alive = false;
    };
  }, [selected, handle]);

  async function enableNotifications() {
    try {
      const p = await Notification.requestPermission();
      setNotifyOn(p === "granted");
      toast({
        title: t(p === "granted" ? "audit.n_on" : "audit.n_off"),
        body: t(p === "granted" ? "audit.n_on_b" : "audit.n_off_b"),
        tone: "info",
      });
    } catch {
      toast({ title: t("audit.n_none"), tone: "info" });
    }
  }

  return (
    <div className="page desk">
      <header className="desk-head">
        <div>
          <h1>{t("nav.audit")}</h1>
          <p className="live">
            <span className="live-dot" aria-hidden /> {t("audit.live")}
          </p>
        </div>
        {!notifyOn && (
          <button className="btn btn-ghost btn-sm" onClick={enableNotifications}>
            <Icon name="bell" size={16} />
            {t("audit.alerts_on")}
          </button>
        )}
      </header>

      <div className="filterbar">
        <div className="search" role="search">
          <label className="sr-only" htmlFor="q">
            {t("audit.search")}
          </label>
          <span className="search-icon">
            <Icon name="search" />
          </span>
          <input id="q" type="search" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={t("audit.search_ph")} />
        </div>
        <label className="fsel">
          {t("filter.currency")}
          <select value={extra.currency} onChange={(e) => setExtra({ ...extra, currency: e.target.value })}>
            <option value="">{t("filter.all")}</option>
            {currencies.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="fsel">
          {t("filter.from")}
          <input type="date" value={extra.from} max={extra.to || undefined} onChange={(e) => setExtra({ ...extra, from: e.target.value })} />
        </label>
        <label className="fsel">
          {t("filter.to")}
          <input type="date" value={extra.to} min={extra.from || undefined} onChange={(e) => setExtra({ ...extra, to: e.target.value })} />
        </label>
        {(filtering || typed) && (
          <button
            className="linkish"
            onClick={() => {
              setExtra(NO_EXTRA);
              setTyped("");
            }}
          >
            {t("filter.clear")}
          </button>
        )}
      </div>

      <div className="filters" role="tablist" aria-label={t("audit.filters")}>
        {FILTERS.map((f) => (
          <button
            key={f.id}
            role="tab"
            aria-selected={filter === f.id}
            className={`filter${filter === f.id ? " is-on" : ""} filter-${f.id}`}
            onClick={() => setFilter(f.id)}
          >
            {t(f.label)}
            {summary && f.count && <span className="filter-n fig">{summary[f.count]}</span>}
          </button>
        ))}
      </div>

      {loadError && (
        <p className="form-error" role="alert">
          {loadError}
        </p>
      )}

      <div className="desk-grid">
        <div className="queue-wrap">
        <ul className="queue" aria-label={t("audit.invoices")}>
          {rows.length === 0 && (
            <li className="queue-empty">
              {filtering
                ? t("filter.none")
                : search.trim()
                  ? t("audit.no_match", { q: search.trim() })
                  : t(filter === "open" ? "audit.empty_open" : "audit.empty")}
            </li>
          )}
          {rows.map((r) => (
            <li key={r.id}>
              <button
                className={`q-row q-${r.status}${selected === r.id ? " is-sel" : ""}${fresh.has(r.id) ? " is-fresh" : ""}`}
                onClick={() => setSelected(r.id)}
                aria-current={selected === r.id}
              >
                <span className="q-bar" aria-hidden />
                <span className="q-main">
                  <span className="q-who">
                    {r.review_state === "new" && <span className="q-new" aria-label={t("audit.new")} />}
                    {r.employee_name}
                  </span>
                  <span className="q-what">
                    #{r.id} {r.vendor || r.filename}
                  </span>
                </span>
                <span className="q-side">
                  <span className="q-amt fig">{amount(r)}</span>
                  <span className="q-when">{ago(r.ts)}</span>
                </span>
                <span className="q-tags">
                  {r.decision ? (
                    <span className={`tag tag-${r.decision}`}>{t(r.decision === "approved" ? "audit.cleared" : "stamp.rejected")}</span>
                  ) : (
                    <span className={`tag tag-${r.status}`}>{t(`status.${r.status}`)}</span>
                  )}
                  {r.violation_ids.map((v) => (
                    <span key={v} className="tag tag-rule fig">
                      {v}
                    </span>
                  ))}
                  {r.warning_count > 0 && <span className="tag tag-warn">{t("audit.warnings", { n: r.warning_count })}</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
        </div>

        <div className="detail" ref={detailRef}>
          {!detail && (
            <div className="sheet detail-empty">
              <p>{t("audit.select")}</p>
            </div>
          )}
          {detail && (
            <Detail
              key={detail.id}
              d={detail}
              onChanged={(d) => {
                setDetail(d);
                refresh();
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function Detail({ d, onChanged }: { d: SubmissionDetail; onChanged: (d: SubmissionDetail) => void }) {
  const toast = useToast();
  const { user } = useAuth();
  const { t, dateTime } = useI18n();
  const own = d.user_id !== null && d.user_id === user?.id;
  const [comment, setComment] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [reopening, setReopening] = useState(false);
  const [busy, setBusy] = useState<null | "approved" | "rejected" | "note" | "reopen">(null);
  const [err, setErr] = useState<string | null>(null);
  const [showDoc, setShowDoc] = useState(true);

  async function run(kind: "approved" | "rejected" | "note" | "reopen", call: () => Promise<SubmissionDetail>, done: string) {
    setBusy(kind);
    setErr(null);
    try {
      const res = await call();
      toast({ title: done, tone: kind === "approved" ? "approved" : kind === "rejected" ? "flagged" : "info" });
      onChanged(res);
      setNote("");
      setReason("");
      setReopening(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("audit.e_save"));
    } finally {
      setBusy(null);
    }
  }

  const decide = (decision: "approved" | "rejected") =>
    run(
      decision,
      () => postJson<SubmissionDetail>(`/api/submissions/${d.id}/decision`, { decision, comment }),
      t(decision === "approved" ? "audit.t_cleared" : "audit.t_rejected", { id: d.id }),
    );

  return (
    <article className="sheet detail-sheet">
      <header className="detail-head">
        <div>
          <p className="fig detail-ref">{t("audit.ref", { id: d.id, when: dateTime(d.ts) })}</p>
          <h2>{d.vendor || d.filename}</h2>
          <p className="detail-amt fig">{moneyConverted(d.result.amount, d.result.currency, d.result.conversion)}</p>
          <p className="detail-who">
            <Avatar name={d.employee_name} size={26} />
            <span>
              {t("audit.sent_by", { name: d.employee_name })}
              {d.employee_email && (
                <>
                  {" "}
                  (<a href={`mailto:${d.employee_email}?subject=Invoice%20%23${d.id}`}>{d.employee_email}</a>)
                </>
              )}
              {d.user_id !== null && (
                <>
                  {" · "}
                  <Link href={`/employees?id=${d.user_id}`}>{t("audit.person")}</Link>
                </>
              )}
            </span>
          </p>
          {d.note && <blockquote className="detail-note">{d.note}</blockquote>}
        </div>
        <div className="detail-stamps">
          <Stamp kind={d.status} size="md" />
          {d.decision && (
            <div className="second-stamp">
              <Stamp kind={d.decision === "approved" ? "paid" : "rejected"} size="md" sub={d.reviewer || undefined} />
            </div>
          )}
        </div>
      </header>

      <ResultView r={{ ...d.result, history_warnings: d.warnings }} />

      <section className="block">
        <div className="doc-head">
          <h3>{t("audit.original")}</h3>
          <button className="linkish" onClick={() => setShowDoc((v) => !v)}>
            {t(showDoc ? "common.hide" : "common.show")}
          </button>
          <a className="linkish" href={fileUrl(d.id)} target="_blank" rel="noreferrer">
            {t("audit.new_tab")}
          </a>
        </div>
        {showDoc &&
          (d.mime === "application/pdf" ? (
            <iframe className="doc" src={fileUrl(d.id)} title={t("audit.doc", { file: d.filename })} />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img className="doc doc-img" src={fileUrl(d.id)} alt={t("audit.doc", { file: d.filename })} />
          ))}
      </section>

      <section className="block">
        <h3>{t("audit.history")}</h3>
        <Timeline events={d.events} />
        <form
          className="note-form"
          onSubmit={(e) => {
            e.preventDefault();
            run("note", () => postJson<SubmissionDetail>(`/api/submissions/${d.id}/notes`, { text: note }), t("audit.t_note"));
          }}
        >
          <label className="fld">
            <span>{t("audit.note")}</span>
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <button className="btn btn-ghost btn-sm" disabled={!note.trim() || busy === "note"}>
            <Icon name="note" size={16} />
            {t("audit.note_add")}
          </button>
        </form>
      </section>

      <section className="block decide">
        <h3>{t(d.decision ? "audit.decision" : "audit.your_decision")}</h3>
        {err && (
          <p className="form-error" role="alert">
            {err}
          </p>
        )}
        {d.decision ? (
          <>
            <p>
              {t("audit.decided", {
                what: t(d.decision === "approved" ? "stamp.paid" : "stamp.rejected"),
                who: d.reviewer || t("common.an_auditor"),
                when: d.decided_at ? dateTime(d.decided_at) : "",
              })}
              {d.decision_comment ? ` “${d.decision_comment}”` : ""}
            </p>
            {!own &&
              (reopening ? (
                <form
                  className="reopen-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    run("reopen", () => postJson<SubmissionDetail>(`/api/submissions/${d.id}/reopen`, { text: reason }), t("audit.t_reopened", { id: d.id }));
                  }}
                >
                  <label className="fld">
                    <span>{t("audit.reopen_why")}</span>
                    <input value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
                  </label>
                  <button className="btn btn-primary btn-sm" disabled={!reason.trim() || busy === "reopen"}>
                    {t("audit.reopen_do")}
                  </button>
                  <button type="button" className="linkish" onClick={() => setReopening(false)}>
                    {t("common.cancel")}
                  </button>
                </form>
              ) : (
                <button className="btn btn-ghost btn-sm reopen-btn" onClick={() => setReopening(true)}>
                  <Icon name="undo" size={16} />
                  {t("audit.reopen")}
                </button>
              ))}
          </>
        ) : own ? (
          <p className="muted">{t("audit.own")}</p>
        ) : (
          <>
            <label className="fld">
              <span>{t("audit.comment")}</span>
              <input value={comment} onChange={(e) => setComment(e.target.value)} />
            </label>
            <p className="hint">{t("audit.recorded", { name: user?.name })}</p>
            <div className="decide-row">
              <button className="btn btn-ok" disabled={!!busy} onClick={() => decide("approved")}>
                <Icon name="check" />
                {t(busy === "approved" ? "audit.clearing" : "audit.clear")}
              </button>
              <button className="btn btn-bad" disabled={!!busy} onClick={() => decide("rejected")}>
                <Icon name="x" />
                {t(busy === "rejected" ? "audit.rejecting" : "audit.reject")}
              </button>
            </div>
          </>
        )}
      </section>
    </article>
  );
}

export default function AuditPage() {
  return (
    <Guard roles={["auditor", "admin"]}>
      <AuditDesk />
    </Guard>
  );
}
