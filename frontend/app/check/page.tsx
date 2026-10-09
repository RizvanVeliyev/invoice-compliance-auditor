"use client";

import { useEffect, useState } from "react";
import ResultView from "@/components/ResultView";
import Stamp from "@/components/Stamp";
import { AnalysisResult, api, postJson } from "@/lib/api";
import { Guard } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

type Sample = { id: string; label: string; text: string };

function QuickCheck() {
  const { t } = useI18n();
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
      const r = await postJson<AnalysisResult>("/api/analyze", { invoice_text: text });
      setResult(r);
      setRun((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("check.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>{t("nav.check")}</h1>
        <p className="lede">
          {t("check.lede")} <a href="/submit">{t("nav.submit")}</a>.
        </p>
      </header>

      <div className="check-grid">
        <div className="check-input">
          {samples.length > 0 && (
            <div className="chips" aria-label={t("check.cases")}>
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
            <span>{t("check.text")}</span>
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
            {t(busy ? "check.busy" : "check.btn")}
          </button>
        </div>

        <div aria-live="polite">
          {!result && !busy && (
            <div className="sheet sheet-empty">
              <p>{t("check.empty")}</p>
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

export default function QuickCheckPage() {
  return (
    <Guard>
      <QuickCheck />
    </Guard>
  );
}
