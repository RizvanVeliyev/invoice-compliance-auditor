"use client";

import { useEffect, useRef, useState } from "react";
import Stamp from "@/components/Stamp";
import { api, money, SubmissionReceipt } from "@/lib/api";

type Sample = { name: string; label: string };
const ACCEPT = "application/pdf,image/png,image/jpeg,image/webp";
const MAX = 5 * 1024 * 1024;

export default function SubmitPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<SubmissionReceipt | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const result = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<Sample[]>("/api/sample-pdfs").then(setSamples).catch(() => setSamples([]));
    try {
      setName(localStorage.getItem("ledger.name") || "");
      setEmail(localStorage.getItem("ledger.email") || "");
    } catch {
      /* no storage: fields start empty */
    }
  }, []);

  function pick(f: File | undefined | null) {
    setError(null);
    setReceipt(null);
    if (!f) return;
    if (!ACCEPT.split(",").includes(f.type) && !f.name.toLowerCase().endsWith(".pdf")) {
      setError(`${f.name} isn't a PDF or an image. Export the invoice as PDF and try again.`);
      return;
    }
    if (f.size > MAX) {
      setError(`${f.name} is ${(f.size / 1048576).toFixed(1)} MB. The limit is 5 MB.`);
      return;
    }
    setFile(f);
  }

  async function loadSample(s: Sample) {
    setError(null);
    try {
      const res = await fetch(`/api/sample-pdfs/${encodeURIComponent(s.name)}`);
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      pick(new File([blob], s.name, { type: "application/pdf" }));
    } catch {
      setError("The sample couldn't be loaded. Check that the backend is running.");
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Add your invoice PDF first.");
      return;
    }
    if (!name.trim()) {
      setError("Enter your name so the audit team knows who sent the invoice.");
      return;
    }
    setBusy(true);
    setError(null);
    setReceipt(null);
    try {
      localStorage.setItem("ledger.name", name);
      localStorage.setItem("ledger.email", email);
    } catch {
      /* ignore */
    }
    const form = new FormData();
    form.append("file", file);
    form.append("employee_name", name);
    form.append("employee_email", email);
    form.append("note", note);
    try {
      const r = await api<SubmissionReceipt>("/api/submissions", { method: "POST", body: form });
      setReceipt(r);
      setTimeout(() => result.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The invoice couldn't be sent.");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setFile(null);
    setReceipt(null);
    setNote("");
    setError(null);
  }

  return (
    <div className="page submit-page">
      <header className="page-head">
        <h1>Submit an invoice</h1>
        <p className="lede">
          Send the invoice for an expense you paid or want paid. It is checked against the expense policy in a few
          seconds, and anything that needs a closer look goes to the audit team.
        </p>
      </header>

      <div className="submit-grid">
        <form className="submit-form" onSubmit={submit} noValidate>
          <div
            className={`tray${drag ? " is-drag" : ""}${file ? " has-file" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              pick(e.dataTransfer.files?.[0]);
            }}
          >
            <input
              ref={input}
              id="file"
              type="file"
              accept={`${ACCEPT},.pdf`}
              className="sr-only"
              onChange={(e) => {
                pick(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <label htmlFor="file" className="tray-inner">
              <span className="tray-paper" aria-hidden>
                <span />
                <span />
                <span />
              </span>
              {file ? (
                <>
                  <span className="tray-title">{file.name}</span>
                  <span className="tray-hint">
                    {(file.size / 1024).toFixed(0)} KB. Choose a different file or drop one here to replace it.
                  </span>
                </>
              ) : (
                <>
                  <span className="tray-title">Drop your invoice PDF here</span>
                  <span className="tray-hint">or click to choose a file. PDF, PNG, JPEG or WEBP up to 5 MB.</span>
                </>
              )}
            </label>
          </div>

          {samples.length > 0 && !file && (
            <div className="samples">
              <span className="samples-label">No invoice to hand? Try one of these:</span>
              <div className="chips">
                {samples.map((s) => (
                  <button type="button" key={s.name} className="chip" onClick={() => loadSample(s)}>
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="row-2">
            <label className="fld">
              <span>Your name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
            </label>
            <label className="fld">
              <span>Work email (optional)</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </label>
          </div>
          <label className="fld">
            <span>Note for the audit team (optional)</span>
            <textarea
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="For example: client visit to Ganja, booked by the travel agency."
            />
          </label>

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <button className="btn btn-primary btn-wide" disabled={busy}>
            {busy ? "Checking your invoice…" : "Send invoice"}
          </button>
        </form>

        <div className="submit-side" ref={result} aria-live="polite">
          {!busy && !receipt && (
            <div className="sheet sheet-empty">
              <p>Your result will appear here once you send the invoice.</p>
              <ul className="expect">
                <li>
                  <Stamp kind="approved" size="sm" /> Passed to Finance for payment
                </li>
                <li>
                  <Stamp kind="flagged" size="sm" /> A rule is broken; the audit team is alerted
                </li>
                <li>
                  <Stamp kind="needs_review" size="sm" /> A person needs to check something
                </li>
              </ul>
            </div>
          )}

          {busy && (
            <div className="sheet sheet-scanning" aria-label="Checking your invoice">
              <div className="ghost-lines" aria-hidden>
                {Array.from({ length: 9 }).map((_, i) => (
                  <span key={i} style={{ width: `${55 + ((i * 37) % 40)}%` }} />
                ))}
              </div>
              <div className="beam beam-loop" aria-hidden />
              <p className="scan-caption">Reading {file?.name} and checking it against 5 policy rules…</p>
            </div>
          )}

          {receipt && (
            <div className={`sheet receipt receipt-${receipt.status}`}>
              <div className="receipt-stamp">
                <Stamp
                  kind={receipt.status}
                  size="lg"
                  sub={receipt.sent_to_audit ? "Sent to audit" : "Cleared"}
                  key={receipt.id}
                />
              </div>
              <p className="receipt-ref fig">Submission #{receipt.id}</p>
              <p className="receipt-msg">{receipt.message}</p>

              <dl className="fields">
                {[
                  ["Vendor", receipt.vendor || "—"],
                  ["Amount", money(receipt.amount, receipt.currency)],
                  ["Category", receipt.category || "—"],
                  ["Date", receipt.date || "—"],
                ].map(([k, v]) => (
                  <div className="field" key={k}>
                    <dt>{k}</dt>
                    <dd className={k === "Amount" ? "fig" : undefined}>{v}</dd>
                  </div>
                ))}
              </dl>

              {receipt.violations.length > 0 && (
                <section className="block">
                  <h3>What breaks the policy</h3>
                  <ol className="findings">
                    {receipt.violations.map((v) => (
                      <li key={v.rule_id} className={`finding sev-${v.severity}`}>
                        <div className="finding-head">
                          <span className="rule-id">{v.rule_id}</span>
                        </div>
                        <p>{v.explanation}</p>
                      </li>
                    ))}
                  </ol>
                </section>
              )}
              {(receipt.review_reasons.length > 0 || receipt.warnings.length > 0) && (
                <section className="block">
                  <h3>Why a person will look at it</h3>
                  <ul className="reasons">
                    {[...receipt.review_reasons, ...receipt.warnings].map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </section>
              )}
              <button className="btn btn-ghost" onClick={reset}>
                Submit another invoice
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
