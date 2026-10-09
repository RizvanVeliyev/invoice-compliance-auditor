import { Status } from "@/lib/api";

const WORDS: Record<string, string> = {
  approved: "Approved",
  flagged: "Flagged",
  needs_review: "Needs review",
  paid: "Cleared to pay",
  rejected: "Rejected",
};

/** A rubber-stamp verdict. `key` it on the value so the landing animation replays. */
export default function Stamp({
  kind,
  size = "md",
  sub,
}: {
  kind: Status | "paid" | "rejected";
  size?: "sm" | "md" | "lg";
  sub?: string;
}) {
  return (
    <div className={`stamp stamp-${kind} stamp-${size}`} role="img" aria-label={WORDS[kind]}>
      <span className="stamp-word">{WORDS[kind]}</span>
      {sub && <span className="stamp-sub">{sub}</span>}
    </div>
  );
}
