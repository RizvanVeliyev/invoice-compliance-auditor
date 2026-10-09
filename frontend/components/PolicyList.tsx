"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DICT } from "@/lib/dict";
import { useI18n } from "@/lib/i18n";

type Policy = {
  company_name: string;
  policy_version: string;
  currency: string;
  accepted_currencies?: string[];
  fx_rates?: Record<string, number> | null;
  rules: { id: string; description: string }[];
};

export default function PolicyList() {
  const { t } = useI18n();
  const [p, setP] = useState<Policy | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    api<Policy>("/api/policy").then(setP).catch(() => setErr(true));
  }, []);
  if (err) return <p className="muted">{t("policy.error")}</p>;
  if (!p) return <p className="muted">{t("policy.loading")}</p>;
  const rates = Object.entries(p.fx_rates || {});
  return (
    <>
      <p className="muted">
        {t("policy.intro", {
          company: p.company_name,
          version: p.policy_version,
          list: (p.accepted_currencies || [p.currency]).join(", "),
        })}{" "}
        {rates.length > 0 &&
          t("policy.rates", { cur: p.currency, rates: rates.map(([c, r]) => `1 ${c} = ${r} ${p.currency}`).join(", ") })}
      </p>
      <ul className="policy">
        {p.rules.map((r) => (
          <li key={r.id}>
            <span className="rule-id">{r.id}</span>
            {/* A rule the dictionary does not know yet (a new one in policy.json) is shown as written. */}
            <span>{`rule.${r.id}` in DICT ? t(`rule.${r.id}`) : r.description}</span>
          </li>
        ))}
        <li>
          <span className="rule-id">DUP</span>
          <span>{t("policy.dup")}</span>
        </li>
      </ul>
    </>
  );
}
