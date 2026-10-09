"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ResultView from "@/components/ResultView";
import Stamp from "@/components/Stamp";
import { useToast } from "@/components/Toasts";
import {
  ago,
  AlertSummary,
  api,
  ApiError,
  fileUrl,
  money,
  setPin,
  STATUS_WORD,
  SubmissionDetail,
  SubmissionRow,
} from "@/lib/api";

type Filter = "open" | "flagged" | "needs_review" | "decided" | "all";
const FILTERS: { id: Filter; label: string; count?: keyof AlertSummary }[] = [
  { id: "open", label: "Open alerts", count: "open" },
  { id: "flagged", label: "Flagged", count: "flagged" },
  { id: "needs_review", label: "Needs review", count: "needs_review" },
  { id: "decided", label: "Decided", count: "decided" },
  { id: "all", label: "All invoices", count: "total" },
];
const POLL_MS = 5000;

function query(f: Filter) {
  if (f === "open") return "?state=open";
  if (f === "decided") return "?state=decided";
  if (f === "flagged" || f === "needs_review") return `?status=${f}&state=open`;
  return "";
}

export default function AuditDesk() {
  const toast = useToast();
  const [locked, setLocked] = useState(false);
  const [pinInput, setPinInput] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("open");
  const [rows, setRows] = useState<SubmissionRow[]>([]);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notifyOn, setNotifyOn] = useState(false);
  const latest = useRef<number | null>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  const handle = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) {
      setLocked(true);
      return;
    }
    setLoadError(e instanceof Error ? e.message : "Something went wrong.");
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [s, list] = await Promise.all([
        api<AlertSummary>("/api/alerts/summary", {}, true),
        api<SubmissionRow[]>(`/api/submissions${query(filter)}`, {}, true),
      ]);
      setLocked(false);
      setLoadError(null);
      setSummary(s);
      setRows(list);
      // New submissions since the last poll: highlight them and raise an alert.
      if (latest.current !== null && s.latest_id > latest.current) {
        const all = await api<SubmissionRow[]>("/api/submissions?limit=20", {}, true);
        const news = all.filter((r) => r.id > (latest.current as number));
        setFresh((prev) => new Set([...Array.from(prev), ...news.map((n) => n.id)]));
        news
          .filter((n) => n.alert)
          .reverse()
          .forEach((n) => {
            const title = `${STATUS_WORD[n.status]} invoice from ${n.employee_name}`;
            const body = `${n.vendor || "Unknown vendor"}, ${n.amount_label}`;
            toast({ title, body, tone: n.status, href: `/audit?id=${n.id}` });
            try {
              if (notifyOn && document.hidden && Notification.permission === "granted") {
                new Notification(`Ledger: ${title}`, { body });
              }
            } catch {
              /* notifications unsupported */
            }
          });
      }
      latest.current = s.latest_id;
      document.title = s.unread > 0 ? `(${s.unread}) Audit desk — Ledger` : "Audit desk — Ledger";
    } catch (e) {
      handle(e);
    }
  }, [filter, handle, toast, notifyOn]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    const id = Number(new URLSearchParams(window.location.search).get("id"));
    if (id) setSelected(id);
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
    api<SubmissionDetail>(`/api/submissions/${selected}`, {}, true)
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

  async function unlock(e: React.FormEvent) {
    e.preventDefault();
    setPin(pinInput.trim());
    try {
      await api("/api/alerts/summary", {}, true);
      setPinError(null);
      setLocked(false);
      refresh();
    } catch {
      setPinError("That PIN isn't right. Ask the Ledger administrator for the auditor PIN.");
    }
  }

  async function enableNotifications() {
    try {
      const p = await Notification.requestPermission();
      setNotifyOn(p === "granted");
      toast({
        title: p === "granted" ? "Desktop alerts turned on" : "Desktop alerts are blocked",
        body: p === "granted" ? "You'll be notified even when this tab is in the background." : "Allow notifications for this site in your browser settings.",
        tone: "info",
      });
    } catch {
      toast({ title: "This browser doesn't support desktop alerts", tone: "info" });
    }
  }

  if (locked) {
    return (
      <div className="page narrow">
        <form className="sheet pin" onSubmit={unlock}>
          <h1>Audit desk</h1>
          <p>Enter the auditor PIN to see submitted invoices and alerts.</p>
          <label className="fld">
            <span>Auditor PIN</span>
            <input
              type="password"
              inputMode="numeric"
              autoFocus
              value={pinInput}
              onChange={(e) => setPinInput(e.target.value)}
            />
          </label>
          {pinError && (
            <p className="form-error" role="alert">
              {pinError}
            </p>
          )}
          <button className="btn btn-primary">Open the audit desk</button>
        </form>
      </div>
    );
  }

  return (
    <div className="page desk">
      <header className="desk-head">
        <div>
          <h1>Audit desk</h1>
          <p className="live">
            <span className="live-dot" aria-hidden /> New submissions appear here automatically.
          </p>
        </div>
        {!notifyOn && (
          <button className="btn btn-ghost btn-sm" onClick={enableNotifications}>
            Turn on desktop alerts
          </button>
        )}
      </header>

      <div className="filters" role="tablist" aria-label="Filter invoices">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            role="tab"
            aria-selected={filter === f.id}
            className={`filter${filter === f.id ? " is-on" : ""} filter-${f.id}`}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
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
        <ul className="queue" aria-label="Invoices">
          {rows.length === 0 && (
            <li className="queue-empty">
              {filter === "open"
                ? "No open alerts. Flagged invoices and anything that needs a person will appear here."
                : "No invoices in this view yet."}
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
                    {r.review_state === "new" && <span className="q-new" aria-label="New" />}
                    {r.employee_name}
                  </span>
                  <span className="q-what">{r.vendor || r.filename}</span>
                </span>
                <span className="q-side">
                  <span className="q-amt fig">{r.amount_label}</span>
                  <span className="q-when">{ago(r.ts)}</span>
                </span>
                <span className="q-tags">
                  {r.decision ? (
                    <span className={`tag tag-${r.decision}`}>{r.decision === "approved" ? "Cleared" : "Rejected"}</span>
                  ) : (
                    <span className={`tag tag-${r.status}`}>{STATUS_WORD[r.status]}</span>
                  )}
                  {r.violation_ids.map((v) => (
                    <span key={v} className="tag tag-rule fig">
                      {v}
                    </span>
                  ))}
                  {r.warning_count > 0 && <span className="tag tag-warn">{r.warning_count} warning{r.warning_count > 1 ? "s" : ""}</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>

        <div className="detail" ref={detailRef}>
          {!detail && (
            <div className="sheet detail-empty">
              <p>Select an invoice to see why it was flagged, the original document and the decision buttons.</p>
            </div>
          )}
          {detail && <Detail key={detail.id} d={detail} onDecided={(d) => { setDetail(d); refresh(); }} />}
        </div>
      </div>
    </div>
  );
}

function Detail({ d, onDecided }: { d: SubmissionDetail; onDecided: (d: SubmissionDetail) => void }) {
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [busy, setBusy] = useState<null | "approved" | "rejected">(null);
  const [err, setErr] = useState<string | null>(null);
  const [showDoc, setShowDoc] = useState(true);

  useEffect(() => {
    try {
      setReviewer(localStorage.getItem("ledger.reviewer") || "");
    } catch {
      /* ignore */
    }
  }, []);

  async function decide(decision: "approved" | "rejected") {
    setBusy(decision);
    setErr(null);
    try {
      try {
        localStorage.setItem("ledger.reviewer", reviewer);
      } catch {
        /* ignore */
      }
      const res = await api<SubmissionDetail>(
        `/api/submissions/${d.id}/decision`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, comment, reviewer }) },
        true,
      );
      toast({
        title: decision === "approved" ? `Invoice #${d.id} cleared to pay` : `Invoice #${d.id} rejected`,
        tone: decision === "approved" ? "approved" : "flagged",
      });
      onDecided(res);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "The decision couldn't be saved.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="sheet detail-sheet">
      <header className="detail-head">
        <div>
          <p className="fig detail-ref">
            Submission #{d.id}, {new Date(d.ts).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}
          </p>
          <h2>{d.vendor || d.filename}</h2>
          <p className="detail-amt fig">{money(d.result.amount, d.result.currency)}</p>
          <p className="detail-who">
            Sent by {d.employee_name}
            {d.employee_email && (
              <>
                {" "}
                (<a href={`mailto:${d.employee_email}?subject=Invoice%20%23${d.id}`}>{d.employee_email}</a>)
              </>
            )}
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
          <h3>Original document</h3>
          <button className="linkish" onClick={() => setShowDoc((v) => !v)}>
            {showDoc ? "Hide" : "Show"}
          </button>
          <a className="linkish" href={fileUrl(d.id)} target="_blank" rel="noreferrer">
            Open in a new tab
          </a>
        </div>
        {showDoc &&
          (d.mime === "application/pdf" ? (
            <iframe className="doc" src={fileUrl(d.id)} title={`Invoice ${d.filename}`} />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img className="doc doc-img" src={fileUrl(d.id)} alt={`Invoice ${d.filename}`} />
          ))}
      </section>

      <section className="block decide">
        <h3>{d.decision ? "Decision" : "Your decision"}</h3>
        {d.decision ? (
          <p>
            {d.decision === "approved" ? "Cleared to pay" : "Rejected"} by {d.reviewer || "an auditor"}
            {d.decided_at ? ` on ${new Date(d.decided_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}` : ""}.
            {d.decision_comment ? ` “${d.decision_comment}”` : ""}
          </p>
        ) : (
          <>
            <div className="row-2">
              <label className="fld">
                <span>Your name</span>
                <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
              </label>
              <label className="fld">
                <span>Comment to the employee (needed to reject)</span>
                <input value={comment} onChange={(e) => setComment(e.target.value)} />
              </label>
            </div>
            {err && (
              <p className="form-error" role="alert">
                {err}
              </p>
            )}
            <div className="decide-row">
              <button className="btn btn-ok" disabled={!!busy} onClick={() => decide("approved")}>
                {busy === "approved" ? "Clearing…" : "Clear to pay"}
              </button>
              <button className="btn btn-bad" disabled={!!busy} onClick={() => decide("rejected")}>
                {busy === "rejected" ? "Rejecting…" : "Reject"}
              </button>
            </div>
          </>
        )}
      </section>
    </article>
  );
}
