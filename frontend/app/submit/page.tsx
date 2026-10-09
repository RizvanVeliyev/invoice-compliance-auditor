"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import Stamp from "@/components/Stamp";
import { api, ApiError, moneyConverted, SubmissionReceipt } from "@/lib/api";
import { Guard, useAuth } from "@/lib/auth";
import { DICT } from "@/lib/dict";
import { useI18n } from "@/lib/i18n";

type Sample = { name: string; label: string };
type Policy = { currency: string; accepted_currencies?: string[]; fx_rates?: Record<string, number> | null };
const ACCEPT = "application/pdf,image/png,image/jpeg,image/webp";
const MAX = 5 * 1024 * 1024;

function SubmitForm() {
  const { user } = useAuth();
  const { t } = useI18n();
  const [note, setNote] = useState("");
  const [currency, setCurrency] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<SubmissionReceipt | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const result = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<Sample[]>("/api/sample-pdfs").then(setSamples).catch(() => setSamples([]));
    api<Policy>("/api/policy").then(setPolicy).catch(() => setPolicy(null));
  }, []);

  const base = policy?.currency || "AZN";
  const currencies = policy?.accepted_currencies || [base];
  const rates = Object.entries(policy?.fx_rates || {});

  function pick(f: File | undefined | null) {
    setError(null);
    setDuplicate(null);
    setReceipt(null);
    if (!f) return;
    if (!ACCEPT.split(",").includes(f.type) && !f.name.toLowerCase().endsWith(".pdf")) {
      setError(t("submit.e_type", { name: f.name }));
      return;
    }
    if (f.size > MAX) {
      setError(t("submit.e_size", { name: f.name, mb: (f.size / 1048576).toFixed(1) }));
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
      setError(t("submit.e_sample"));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError(t("submit.e_nofile"));
      return;
    }
    setBusy(true);
    setError(null);
    setDuplicate(null);
    setReceipt(null);
    const form = new FormData();
    form.append("file", file);
    form.append("note", note);
    form.append("currency", currency);
    try {
      const r = await api<SubmissionReceipt>("/api/submissions", { method: "POST", body: form });
      setReceipt(r);
    } catch (err) {
      // 409: the server refused the upload because this invoice is already in FiscalAI.
      if (err instanceof ApiError && err.status === 409) setDuplicate(err.message);
      else setError(err instanceof Error ? err.message : t("submit.e_send"));
    } finally {
      setBusy(false);
      setTimeout(() => result.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50);
    }
  }

  function reset() {
    setFile(null);
    setReceipt(null);
    setDuplicate(null);
    setNote("");
    setError(null);
  }

  const message = (r: SubmissionReceipt) =>
    t(r.status === "approved" && !r.sent_to_audit ? "submit.msg_ok" : r.status === "flagged" ? "submit.msg_flagged" : "submit.msg_review");

  return (
    <div className="page submit-page">
      <header className="page-head">
        <h1>{t("nav.submit")}</h1>
        <p className="lede">{t("submit.lede")}</p>
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
                  <span className="tray-hint">{t("submit.replace", { kb: (file.size / 1024).toFixed(0) })}</span>
                </>
              ) : (
                <>
                  <span className="tray-title">{t("submit.drop")}</span>
                  <span className="tray-hint">{t("submit.drop_hint")}</span>
                </>
              )}
            </label>
          </div>

          {samples.length > 0 && !file && (
            <div className="samples">
              <span className="samples-label">{t("submit.samples")}</span>
              <div className="chips">
                {samples.map((s) => (
                  <button type="button" key={s.name} className="chip" onClick={() => loadSample(s)}>
                    {`sample.${s.name}` in DICT ? t(`sample.${s.name}`) : s.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="row-2">
            <div className="fld">
              <span>{t("submit.by")}</span>
              <p className="readonly">
                {user?.name}
                <span className="muted"> ({user?.email})</span>
              </p>
            </div>
            <label className="fld">
              <span>{t("submit.currency")}</span>
              <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
                <option value="">{t("submit.currency_auto")}</option>
                {currencies.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="hint">
            {t("submit.accepts", { list: currencies.join(", ") })}{" "}
            {rates.length > 0 &&
              t("submit.rates", { cur: base, rates: rates.map(([c, r]) => `1 ${c} = ${r} ${base}`).join(", ") })}{" "}
            {t("submit.currency_only")}
          </p>
          <label className="fld">
            <span>{t("submit.note")}</span>
            <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("submit.note_ph")} />
          </label>

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <button className="btn btn-primary btn-wide" disabled={busy}>
            {t(busy ? "submit.sending" : "submit.send")}
          </button>
        </form>

        <div className="submit-side" ref={result} aria-live="polite">
          {!busy && !receipt && !duplicate && (
            <div className="sheet sheet-empty">
              <p>{t("submit.empty")}</p>
              <ul className="expect">
                <li>
                  <Stamp kind="approved" size="sm" /> {t("submit.x_ok")}
                </li>
                <li>
                  <Stamp kind="flagged" size="sm" /> {t("submit.x_flag")}
                </li>
                <li>
                  <Stamp kind="needs_review" size="sm" /> {t("submit.x_review")}
                </li>
              </ul>
              <p className="hint">
                {t("submit.follow")} <Link href="/my">{t("nav.my")}</Link>.
              </p>
            </div>
          )}

          {busy && (
            <div className="sheet sheet-scanning" aria-label={t("submit.sending")}>
              <div className="ghost-lines" aria-hidden>
                {Array.from({ length: 9 }).map((_, i) => (
                  <span key={i} style={{ width: `${55 + ((i * 37) % 40)}%` }} />
                ))}
              </div>
              <div className="beam beam-loop" aria-hidden />
              <p className="scan-caption">{t("submit.scan", { file: file?.name })}</p>
            </div>
          )}

          {duplicate && !busy && (
            <div className="sheet receipt receipt-duplicate" role="alert">
              <div className="receipt-stamp">
                <Stamp kind="duplicate" size="lg" sub={t("stamp.not_accepted")} />
              </div>
              <p className="receipt-ref fig">{file?.name}</p>
              <p className="receipt-msg">{t("submit.dup")}</p>
              <p>{duplicate}</p>
              <div className="cta-row">
                <Link href="/my" className="btn btn-primary">
                  {t("submit.see_my")}
                </Link>
                <button className="btn btn-ghost" onClick={reset}>
                  {t("submit.different")}
                </button>
              </div>
            </div>
          )}

          {receipt && (
            <div className={`sheet receipt receipt-${receipt.status}`}>
              <div className="receipt-stamp">
                <Stamp
                  kind={receipt.status}
                  size="lg"
                  sub={t(receipt.sent_to_audit ? "stamp.sent_to_audit" : "stamp.cleared")}
                  key={receipt.id}
                />
              </div>
              <p className="receipt-ref fig">{t("submit.ref", { id: receipt.id })}</p>
              <p className="receipt-msg">{message(receipt)}</p>

              <dl className="fields">
                {[
                  ["f.vendor", receipt.vendor || "—"],
                  ["f.amount", moneyConverted(receipt.amount, receipt.currency, receipt.conversion)],
                  ["f.category", receipt.category || "—"],
                  ["f.date", receipt.date || "—"],
                ].map(([k, v]) => (
                  <div className="field" key={k}>
                    <dt>{t(k)}</dt>
                    <dd className={k === "f.amount" ? "fig" : undefined}>{v}</dd>
                  </div>
                ))}
              </dl>
              {receipt.conversion && (
                <p className="hint">
                  {t("submit.fx", { from: receipt.conversion.from, rate: receipt.conversion.rate, to: receipt.conversion.to })}
                </p>
              )}

              {receipt.violations.length > 0 && (
                <section className="block">
                  <h3>{t("submit.breaks")}</h3>
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
                  <h3>{t("submit.why")}</h3>
                  <ul className="reasons">
                    {[...receipt.review_reasons, ...receipt.warnings].map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </section>
              )}
              <div className="cta-row">
                <button className="btn btn-ghost" onClick={reset}>
                  {t("submit.another")}
                </button>
                <Link href="/my" className="btn btn-ghost">
                  {t("nav.my")}
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function SubmitPage() {
  return (
    <Guard>
      <SubmitForm />
    </Guard>
  );
}
