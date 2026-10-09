import { AnalysisResult, money } from "@/lib/api";

/** Findings, warnings and calculation trace for one checked invoice (auditor & quick check). */
export default function ResultView({ r, compact = false }: { r: AnalysisResult; compact?: boolean }) {
  const reasons = r.needs_review_reasons || [];
  const warnings = r.history_warnings || [];
  const trace = (r.trace || []).filter((t) => t.result !== "n/a");
  return (
    <div className="result">
      <dl className="fields">
        {[
          ["Vendor", r.vendor || "—"],
          ["Amount", money(r.amount, r.currency)],
          ["Category", r.category || "—"],
          ["Date", r.date || "—"],
          ["Employee on invoice", r.employee || "—"],
          ["Approval needed", r.required_approval_level || "—"],
        ].map(([k, v]) => (
          <div key={k} className="field">
            <dt>{k}</dt>
            <dd className={k === "Amount" ? "fig" : undefined}>{v}</dd>
          </div>
        ))}
      </dl>

      {r.violations.length > 0 && (
        <section className="block">
          <h3>Rules broken</h3>
          <ol className="findings">
            {r.violations.map((v) => (
              <li key={v.rule_id} className={`finding sev-${v.severity}`}>
                <div className="finding-head">
                  <span className="rule-id">{v.rule_id}</span>
                  <span className="sev">{v.severity} severity</span>
                </div>
                <p>{v.explanation}</p>
                {!compact && v.rule_description && <p className="rule-text">Policy: {v.rule_description}</p>}
              </li>
            ))}
          </ol>
        </section>
      )}

      {(reasons.length > 0 || warnings.length > 0) && (
        <section className="block">
          <h3>Needs a person because</h3>
          <ul className="reasons">
            {reasons.map((x, i) => (
              <li key={`r${i}`}>{x}</li>
            ))}
            {warnings.map((x, i) => (
              <li key={`w${i}`} className="reason-warn">
                {x}
              </li>
            ))}
          </ul>
        </section>
      )}

      {r.violations.length === 0 && reasons.length === 0 && warnings.length === 0 && (
        <p className="clean">Every rule that applies to this invoice passed.</p>
      )}

      {trace.length > 0 && (
        <section className="block">
          <h3>How each rule was checked</h3>
          <table className="trace">
            <tbody>
              {trace.map((t, i) => (
                <tr key={i} className={`t-${t.result}`}>
                  <th scope="row">{t.rule_id}</th>
                  <td className="t-res">{t.result}</td>
                  <td className="fig">{t.calc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {r.meta && (
        <p className="meta">
          Fields read by {r.meta.provider === "offline" ? "the offline reader" : `the ${r.meta.provider} model`}
          {r.meta.source ? ` from ${r.meta.source.replace(/-/g, " ")}` : ""}; verdict decided by the policy rules.
          {typeof r.meta.latency_ms === "number" ? ` Took ${r.meta.latency_ms} ms.` : ""}
          {r.meta.audit_logged === false ? " Warning: not written to the audit log." : ""}
        </p>
      )}
    </div>
  );
}
