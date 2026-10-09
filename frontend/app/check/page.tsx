"use client";

import { useEffect, useState } from "react";
import ResultView from "@/components/ResultView";
import Stamp from "@/components/Stamp";
import { AnalysisResult, api } from "@/lib/api";

type Sample = { id: string; label: string; text: string };

export default function QuickCheck() {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [run, setRun] = useState(0);

  useEffect(() => {
    api<Sample[]>("/api/samples").then(setSamples).catch(() => setSamples([]));
  }, []);

  async function check() {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<AnalysisResult>("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invoice_text: text }),
      });
      setResult(r);
      setRun((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The check failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Quick check</h1>
        <p className="lede">
          Paste an invoice or expense record to see how the policy treats it. Nothing is sent to the audit team from
          here; to submit a real invoice, use <a href="/submit">Submit an invoice</a>.
        </p>
      </header>

      <div className="check-grid">
        <div className="check-input">
          {samples.length > 0 && (
            <div className="chips" aria-label="Test cases">
              {samples.map((s) => (
                <button
                  key={s.id}
                  className={`chip${active === s.id ? " is-on" : ""}`}
                  onClick={() => {
                    setActive(s.id);
                    setText(s.text);
                    setResult(null);
                  }}
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}
          <label className="fld">
            <span>Invoice text</span>
            <textarea
              className="paste"
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setActive(null);
              }}
              placeholder={"Vendor: …\nDate: …\nAmount: …\nCategory: …\nApproval: …"}
            />
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="btn btn-primary btn-wide" onClick={check} disabled={busy || !text.trim()}>
            {busy ? "Checking…" : "Check against policy"}
          </button>
        </div>

        <div aria-live="polite">
          {!result && !busy && (
            <div className="sheet sheet-empty">
              <p>Pick a test case or paste an invoice, then check it.</p>
            </div>
          )}
          {busy && (
            <div className="sheet sheet-scanning">
              <div className="ghost-lines" aria-hidden>
                {Array.from({ length: 7 }).map((_, i) => (
                  <span key={i} style={{ width: `${50 + ((i * 41) % 45)}%` }} />
                ))}
              </div>
              <div className="beam beam-loop" aria-hidden />
            </div>
          )}
          {result && !busy && (
            <div className="sheet receipt">
              <div className="receipt-stamp">
                <Stamp kind={result.status} size="lg" key={run} />
              </div>
              <ResultView r={result} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
