"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useState } from "react";
import { useI18n } from "@/lib/i18n";

type Tone = "flagged" | "needs_review" | "approved" | "info";
type Toast = { id: number; title: string; body?: string; tone: Tone; href?: string };

const Ctx = createContext<(t: Omit<Toast, "id">) => void>(() => {});

export function useToast() {
  return useContext(Ctx);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const { t: tr } = useI18n();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((xs) => [...xs.slice(-3), { ...t, id }]);
    setTimeout(() => setToasts((xs) => xs.filter((x) => x.id !== id)), 7000);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            <div className="toast-title">{t.title}</div>
            {t.body && <div className="toast-body">{t.body}</div>}
            {t.href && (
              <Link className="toast-link" href={t.href}>
                {tr("common.open")}
              </Link>
            )}
            <button
              className="toast-close"
              aria-label={tr("common.dismiss")}
              onClick={() => setToasts((xs) => xs.filter((x) => x.id !== t.id))}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
