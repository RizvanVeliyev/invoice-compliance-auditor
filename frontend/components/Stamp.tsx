"use client";

import { Status } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** A rubber-stamp verdict. `key` it on the value so the landing animation replays. */
export default function Stamp({
  kind,
  size = "md",
  sub,
}: {
  kind: Status | "paid" | "rejected" | "duplicate";
  size?: "sm" | "md" | "lg";
  sub?: string;
}) {
  const { t } = useI18n();
  const word = t(`stamp.${kind}`);
  return (
    <div className={`stamp stamp-${kind} stamp-${size}`} role="img" aria-label={word}>
      <span className="stamp-word">{word}</span>
      {sub && <span className="stamp-sub">{sub}</span>}
    </div>
  );
}
