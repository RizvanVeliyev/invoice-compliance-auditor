// All calls are same-origin; next.config.js forwards /api/* to the FastAPI backend.

export type Status = "approved" | "flagged" | "needs_review";

export type Violation = {
  rule_id: string;
  rule_description?: string;
  explanation: string;
  severity: "low" | "medium" | "high";
};

export type TraceRow = { rule_id: string; result: string; calc: string };

export type AnalysisResult = {
  vendor: string;
  amount: number | null;
  currency: string;
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
  amount: number | null;
  currency: string;
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
  filename: string;
  status: Status;
  alert: boolean;
  review_state: "new" | "seen" | "decided" | "auto_cleared";
  decision: "approved" | "rejected" | null;
  vendor: string;
  amount: number | null;
  currency: string;
  amount_label: string;
  category: string;
  violation_ids: string[];
  warning_count: number;
};

export type SubmissionDetail = SubmissionRow & {
  note: string;
  mime: string;
  size: number;
  decision_comment: string | null;
  reviewer: string | null;
  decided_at: string | null;
  warnings: string[];
  result: AnalysisResult;
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

const PIN_KEY = "ledger.auditorPin";

export function getPin(): string {
  try {
    return sessionStorage.getItem(PIN_KEY) || "";
  } catch {
    return "";
  }
}

export function setPin(pin: string) {
  try {
    sessionStorage.setItem(PIN_KEY, pin);
  } catch {
    /* storage unavailable: PIN lives for this page only */
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init: RequestInit = {}, auditor = false): Promise<T> {
  const headers = new Headers(init.headers);
  if (auditor && getPin()) headers.set("X-Auditor-Pin", getPin());
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Ledger's server can't be reached. Check that the backend is running.");
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : `Request failed (${res.status}).`);
  }
  return data as T;
}

export function fileUrl(id: number) {
  const pin = getPin();
  return `/api/submissions/${id}/file${pin ? `?pin=${encodeURIComponent(pin)}` : ""}`;
}

export function money(amount: number | null | undefined, currency?: string) {
  if (amount === null || amount === undefined) return "—";
  const n = amount.toLocaleString("en-US", { minimumFractionDigits: amount % 1 ? 2 : 0, maximumFractionDigits: 2 });
  return `${n} ${currency || ""}`.trim();
}

export function ago(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export const STATUS_WORD: Record<Status, string> = {
  approved: "Approved",
  flagged: "Flagged",
  needs_review: "Needs review",
};
