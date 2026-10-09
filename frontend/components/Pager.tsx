"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";

/** Previous / next with "21–40 of 57". Renders nothing when everything fits on one page. */
export default function Pager({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
}) {
  const { t } = useI18n();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav className="pager" aria-label={t("pager.label")}>
      <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        {t("pager.prev")}
      </button>
      <span className="pager-info fig" aria-live="polite">
        {t("pager.range", { from, to, total })}
      </span>
      <button className="btn btn-ghost btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        {t("pager.next")}
      </button>
    </nav>
  );
}

/** Paging for a list that is already in memory. Steps back to the last page when the list shrinks. */
export function usePaged<T>(items: T[], pageSize: number) {
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);
  const current = Math.min(page, pages);
  return { page: current, setPage, pageSize, total: items.length, rows: items.slice((current - 1) * pageSize, current * pageSize) };
}
