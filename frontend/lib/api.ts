import { translate } from "@/lib/i18n";

// All calls are same-origin; next.config.js forwards /api/* to the FastAPI backend.
// The session lives in an HttpOnly cookie, so nothing here ever handles a token.

export type Status = "approved" | "flagged" | "needs_review";
export type Role = "employee" | "auditor" | "admin";

export type User = {
  id: number;
  email: string;
  name: string;
  role: Role;
  active: boolean;
  created_at: string;
  last_login: string | null;
  /** "auditor" while the admin has not yet answered this person's request for auditor access. */
  requested_role: Role | null;
};

export type AuthState = { user: User | null; setup_required: boolean };

export type Violation = {
  rule_id: string;
  rule_description?: string;
  explanation: string;
  severity: "low" | "medium" | "high";
};

export type TraceRow = { rule_id: string; result: string; calc: string };

/** Set when the invoice is priced in USD or EUR: limits are checked on the converted figure. */
export type Conversion = { from: string; to: string; rate: number; amount: number; converted: number };

export type AnalysisResult = {
  vendor: string;
  invoice_number?: string;
  amount: number | null;
  currency: string;
  amount_policy?: number | null;
  policy_currency?: string;
  conversion?: Conversion | null;
  category: string;
  date: string;
  employee: string;
  violations: Violation[];
  status: Status;
  required_approval_level: string;
  confidence: "high" | "medium" | "low";
  notes: string;
  trace?: TraceRow[];
  needs_review_reasons?: string[];
  assumptions?: string[];
  approval_verification?: "none" | "verified" | "unverified" | "rejected";
  security_flags?: string[];
  history_warnings?: string[];
  meta?: {
    provider: string;
    source: string;
    latency_ms?: number;
    input_tokens?: number;
    output_tokens?: number;
    estimated_cost_usd?: number | null;
    audit_logged?: boolean;
  };
};

export type SubmissionReceipt = {
  id: number;
  status: Status;
  sent_to_audit: boolean;
  message: string;
  vendor: string;
  invoice_number: string;
  amount: number | null;
  currency: string;
  conversion: Conversion | null;
  category: string;
  date: string;
  employee: string;
  violations: Violation[];
  review_reasons: string[];
  warnings: string[];
};

export type SubmissionRow = {
  id: number;
  ts: string;
  employee_name: string;
  employee_email: string;
  user_id: number | null;
  filename: string;
  status: Status;
  alert: boolean;
  review_state: "new" | "seen" | "decided" | "auto_cleared";
  decision: "approved" | "rejected" | null;
  vendor: string;
  invoice_number: string;
  amount: number | null;
  currency: string;
  amount_label: string;
  conversion: Conversion | null;
  category: string;
  violation_ids: string[];
  warning_count: number;
};

/** One line of a submission's history. Notes are internal to the audit team. */
export type TimelineEvent = {
  id: number;
  ts: string;
  user_name: string;
  kind: "submitted" | "approved" | "rejected" | "reopened" | "note" | "email" | "email_failed";
  text: string;
};

/** Spending for one person (or everyone): by month, category and vendor, in the policy currency. */
export type SpendReport = {
  policy_currency: string;
  totals: { count: number; approved: number; flagged: number; needs_review: number; in_review: number; cleared: number; rejected: number };
  money: { amount: number; cleared: number; in_review: number; rejected: number };
  months: { month: string; count: number; amount: number; cleared: number; in_review: number; rejected: number }[];
  by_category: { category: string; count: number; amount: number }[];
  top_vendors: { vendor: string; count: number; amount: number }[];
};

export type Person = {
  id: number;
  name: string;
  email: string;
  role: Role;
  active: boolean;
  count: number;
  amount: number;
  flagged: number;
  rejected: number;
  in_review: number;
  last_submission: string | null;
};

export type PersonDetail = { user: User; report: SpendReport; submissions: SubmissionRow[] };

export type SubmissionDetail = SubmissionRow & {
  events: TimelineEvent[];
  note: string;
  mime: string;
  size: number;
  decision_comment: string | null;
  reviewer: string | null;
  decided_at: string | null;
  warnings: string[];
  result: AnalysisResult;
};

export type Outcome = "in_review" | "cleared" | "rejected";

/** One of the signed-in employee's own invoices, with what happened to it. */
export type MySubmission = SubmissionRow & {
  outcome: Outcome;
  events: TimelineEvent[];
  note: string;
  date: string;
  decision_comment: string | null;
  reviewer: string | null;
  decided_at: string | null;
  violations: Violation[];
  review_reasons: string[];
};

export type AlertSummary = {
  unread: number;
  open: number;
  flagged: number;
  needs_review: number;
  decided: number;
  total: number;
  latest_id: number;
};

export type Overview = {
  policy_currency: string;
  fx_rates: Record<string, number>;
  counts: {
    total: number;
    approved: number;
    flagged: number;
    needs_review: number;
    in_review: number;
    cleared: number;
    auto_cleared: number;
    rejected: number;
    duplicates_blocked: number;
  };
  money: { submitted: number; cleared: number; in_review: number; rejected: number };
  unconverted: number;
  avg_decision_hours: number | null;
  decisions: number;
  by_currency: { currency: string; count: number; amount: number; amount_policy: number }[];
  by_rule: { rule_id: string; count: number; description: string }[];
  by_employee: { name: string; count: number; flagged: number; rejected: number; amount_policy: number }[];
  by_day: { date: string; approved: number; flagged: number; needs_review: number }[];
  recent_decisions: {
    id: number;
    decided_at: string;
    reviewer: string;
    decision: "approved" | "rejected";
    comment: string;
    employee_name: string;
    label: string;
    amount_label: string;
  }[];
  by_auditor: { name: string; count: number }[];
  recent_blocks: { id: number; ts: string; user_name: string; filename: string; original_id: number; reason: string }[];
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Fired when the server says the session is gone, so the app can send the person to sign in. */
export const SIGNED_OUT_EVENT = "ledger:signed-out";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { ...init, cache: "no-store", credentials: "same-origin" });
  } catch {
    throw new ApiError(0, translate("common.no_server"));
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : translate("common.request_failed", { n: res.status }));
  }
  return data as T;
}

/** One page of a list: the rows, and how many rows match in total (from the X-Total-Count header). */
export async function apiPage<T>(path: string): Promise<{ rows: T[]; total: number }> {
  let res: Response;
  try {
    res = await fetch(path, { cache: "no-store", credentials: "same-origin" });
  } catch {
    throw new ApiError(0, translate("common.no_server"));
  }
  if (!res.ok) {
    if (res.status === 401) window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
    throw new ApiError(res.status, translate("common.request_failed", { n: res.status }));
  }
  const rows = (await res.json()) as T[];
  const total = Number(res.headers.get("X-Total-Count"));
  return { rows, total: Number.isFinite(total) && total > 0 ? total : rows.length };
}

export function postJson<T>(path: string, body: unknown, method = "POST") {
  return api<T>(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export function fileUrl(id: number) {
  return `/api/submissions/${id}/file`;
}

export function money(amount: number | null | undefined, currency?: string) {
  if (amount === null || amount === undefined) return "—";
  const n = amount.toLocaleString("en-US", { minimumFractionDigits: amount % 1 ? 2 : 0, maximumFractionDigits: 2 });
  return `${n} ${currency || ""}`.trim();
}

/** "650 USD = 1,105 AZN" for a converted invoice, otherwise just the amount. */
export function moneyConverted(amount: number | null | undefined, currency: string, c?: Conversion | null) {
  return c ? `${money(amount, currency)} = ${money(c.converted, c.to)}` : money(amount, currency);
}

export const isAuditor = (u: User | null | undefined) => !!u && (u.role === "auditor" || u.role === "admin");
