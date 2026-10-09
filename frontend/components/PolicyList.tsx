"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Policy = { company_name: string; policy_version: string; rules: { id: string; description: string }[] };

export default function PolicyList() {
  const [p, setP] = useState<Policy | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    api<Policy>("/api/policy").then(setP).catch(() => setErr(true));
  }, []);
  if (err) return <p className="muted">The policy couldn&apos;t be loaded. Start the backend and refresh.</p>;
  if (!p) return <p className="muted">Loading the policy…</p>;
  return (
    <ul className="policy">
      {p.rules.map((r) => (
        <li key={r.id}>
          <span className="rule-id">{r.id}</span>
          <span>{r.description}</span>
        </li>
      ))}
    </ul>
  );
}
