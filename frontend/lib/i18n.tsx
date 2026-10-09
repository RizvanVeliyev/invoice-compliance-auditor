"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { DICT, Lang, LANGS } from "@/lib/dict";

type Vars = Record<string, string | number | null | undefined>;
const INDEX: Record<Lang, number> = { en: 0, az: 1, ru: 2 };
const STORE = "ledger.lang";

// Month names for every language, so a date reads the same in any browser. (Many browsers ship
// without Azerbaijani month names and print "M10" instead.)
const MONTHS: Record<Lang, { short: string[]; long: string[] }> = {
  en: {
    short: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    long: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
  },
  az: {
    short: ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avq", "sen", "okt", "noy", "dek"],
    long: ["Yanvar", "Fevral", "Mart", "Aprel", "May", "İyun", "İyul", "Avqust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"],
  },
  ru: {
    short: ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    long: ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"],
  },
};
const two = (n: number) => String(n).padStart(2, "0");

// The language in use, for code outside React (the fetch helper's own error messages).
let current: Lang = "en";

function render(lang: Lang, key: string, vars?: Vars) {
  const row = DICT[key];
  const text = row ? row[INDEX[lang]] : key;
  return vars ? text.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? "")) : text;
}

export function translate(key: string, vars?: Vars) {
  return render(current, key, vars);
}

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Vars) => string;
  /** "9 Oct 2026" */
  date: (iso: string) => string;
  /** "9 Oct 2026, 15:40" */
  dateTime: (iso: string) => string;
  /** "9 Oct" */
  day: (iso: string) => string;
  /** "3 min ago", then a short date */
  ago: (iso: string) => string;
  /** "2026-10" -> "Oct", or "October 2026" when long */
  month: (yearMonth: string, long?: boolean) => string;
};

const I18nCtx = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  // The pages are prerendered in English; the visitor's own language is applied as soon as the page loads.
  useEffect(() => {
    let pick: Lang | null = null;
    try {
      const saved = localStorage.getItem(STORE);
      if (saved && saved in INDEX) pick = saved as Lang;
    } catch {
      /* storage unavailable */
    }
    if (!pick) {
      const nav = (navigator.language || "").toLowerCase();
      pick = nav.startsWith("az") ? "az" : nav.startsWith("ru") ? "ru" : "en";
    }
    setLangState(pick);
  }, []);

  useEffect(() => {
    current = lang;
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    current = l;
    setLangState(l);
    try {
      localStorage.setItem(STORE, l);
    } catch {
      /* the choice lasts for this page only */
    }
  }, []);

  const value = useMemo<Ctx>(() => {
    const t = (key: string, vars?: Vars) => render(lang, key, vars);
    const names = MONTHS[lang];
    const parse = (iso: string) => {
      const d = new Date(iso);
      return isNaN(d.getTime()) ? null : d;
    };
    const day = (iso: string) => {
      const d = parse(iso);
      return d ? `${d.getDate()} ${names.short[d.getMonth()]}` : iso;
    };
    const date = (iso: string) => {
      const d = parse(iso);
      return d ? `${day(iso)} ${d.getFullYear()}` : iso;
    };
    return {
      lang,
      setLang,
      t,
      date,
      dateTime: (iso) => {
        const d = parse(iso);
        return d ? `${date(iso)}, ${two(d.getHours())}:${two(d.getMinutes())}` : iso;
      },
      day,
      ago: (iso) => {
        const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
        if (s < 45) return t("time.now");
        if (s < 3600) return t("time.min", { n: Math.round(s / 60) });
        if (s < 86400) return t("time.hour", { n: Math.round(s / 3600) });
        return day(iso);
      },
      month: (ym, long = false) => {
        const [y, m] = ym.split("-").map(Number);
        if (!y || !m || m < 1 || m > 12) return ym;
        return long ? `${names.long[m - 1]} ${y}` : names.short[m - 1];
      },
    };
  }, [lang, setLang]);

  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nCtx);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}

/** AZ | EN | RU switch shown in the top bar. */
export function LanguageSwitch() {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="langs" role="group" aria-label={t("nav.language")}>
      {LANGS.map((l) => (
        <button
          key={l.id}
          type="button"
          lang={l.id}
          title={l.name}
          aria-pressed={lang === l.id}
          className={`lang${lang === l.id ? " is-on" : ""}`}
          onClick={() => setLang(l.id)}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
