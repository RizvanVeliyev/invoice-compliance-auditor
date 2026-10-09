"use client";

import { AnalysisResult, moneyConverted } from "@/lib/api";
import { DICT } from "@/lib/dict";
import { useI18n } from "@/lib/i18n";

/** Findings, warnings and calculation trace for one checked invoice (auditor & quick check). */
export default function ResultView({ r, compact = false }: { r: AnalysisResult; compact?: boolean }) {
  const { t } = useI18n();
  const reasons = r.needs_review_reasons || [];
  const warnings = r.history_warnings || [];
  const trace = (r.trace || []).filter((x) => x.result !== "n/a");
  const word = (prefix: string, value: string) => (`${prefix}.${value}` in DICT ? t(`${prefix}.${value}`) : value);
  return (
    <div className="result">
      <dl className="fields">
        {[
          ["f.vendor", r.vendor || "—"],
          ["f.amount", moneyConverted(r.amount, r.currency, r.conversion)],
          ["f.invoice_no", r.invoice_number || "—"],
          ["f.category", r.category || "—"],
          ["f.date", r.date || "—"],
          ["f.employee_on", r.employee || "—"],
          ["f.approval_needed", r.required_approval_level || "—"],
        ].map(([k, v]) => (
          <div key={k} className="field">
            <dt>{t(k)}</dt>
            <dd className={k === "f.amount" ? "fig" : undefined}>{v}</dd>
          </div>
        ))}
      </dl>

      {r.violations.length > 0 && (
        <section className="block">
          <h3>{t("result.broken")}</h3>
          <ol className="findings">
            {r.violations.map((v) => (
              <li key={v.rule_id} className={`finding sev-${v.severity}`}>
                <div className="finding-head">
                  <span className="rule-id">{v.rule_id}</span>
                  <span className="sev">{t("result.severity", { sev: t(`sev.${v.severity}`) })}</span>
                </div>
                <p>{v.explanation}</p>
                {!compact && v.rule_description && (
                  <p className="rule-text">
                    {t("result.policy", { text: word("rule", v.rule_id) === v.rule_id ? v.rule_description : word("rule", v.rule_id) })}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      {(reasons.length > 0 || warnings.length > 0) && (
        <section className="block">
          <h3>{t("result.person")}</h3>
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
        <p className="clean">{t("result.clean")}</p>
      )}

      {trace.length > 0 && (
        <section className="block">
          <h3>{t("result.how")}</h3>
          <table className="trace">
            <tbody>
              {trace.map((x, i) => (
                <tr key={i} className={`t-${x.result}`}>
                  <th scope="row">{x.rule_id}</th>
                  <td className="t-res">{word("res", x.result)}</td>
                  <td className="fig">{x.calc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {r.meta && (
        <p className="meta">
          {r.meta.provider === "offline" ? t("result.meta_offline") : t("result.meta_model", { provider: r.meta.provider })}
          {typeof r.meta.latency_ms === "number" ? ` ${t("result.took", { ms: r.meta.latency_ms })}` : ""}
          {r.meta.audit_logged === false ? ` ${t("result.not_logged")}` : ""}
        </p>
      )}
    </div>
  );
}
