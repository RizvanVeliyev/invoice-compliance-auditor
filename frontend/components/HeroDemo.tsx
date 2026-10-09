"use client";

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import Stamp from "./Stamp";

type Example = {
  n: 1 | 2 | 3; // picks the translated tab, category, description, approval and calculation
  vendor: string;
  no: string;
  employee: string;
  amount: string;
  focus: number; // index of the row the check is about
  verdict: "approved" | "flagged" | "needs_review";
  rule: string;
};

const EXAMPLES: Example[] = [
  { n: 1, vendor: "Baku Business Hotel", no: "BBH-88310", employee: "Murad Quliyev", amount: "1,140.00 AZN", focus: 3, verdict: "flagged", rule: "EXP-1.2" },
  { n: 2, vendor: "City Catering Group", no: "CCG-24117", employee: "Aysel Karimova", amount: "390.00 AZN", focus: 3, verdict: "approved", rule: "EXP-1.1" },
  { n: 3, vendor: "Caspian Office Supplies", no: "COS-7702", employee: "Tural Ismayilov", amount: "410.00 AZN", focus: 1, verdict: "needs_review", rule: "" },
];

// phase: 0 ink, 1 scanning, 2 calculation, 3 stamped
export default function HeroDemo() {
  const { t } = useI18n();
  const [ix, setIx] = useState(0);
  const [run, setRun] = useState(0);
  const [phase, setPhase] = useState(0);
  const [typed, setTyped] = useState(0);
  const wrap = useRef<HTMLDivElement>(null);
  const ex = EXAMPLES[ix];
  const calc = t(`hero.k${ex.n}`);
  const rows: [string, string, boolean][] = [
    [t("hero.employee"), ex.employee, false],
    [t("hero.category"), t(`hero.c${ex.n}`), false],
    [t("hero.description"), t(`hero.d${ex.n}`), false],
    [t("hero.amount"), ex.amount, true],
    [t("hero.approval"), t(`hero.a${ex.n}`), false],
  ];

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setPhase(3);
      setTyped(calc.length);
      return;
    }
    setPhase(0);
    setTyped(0);
    const ts = [setTimeout(() => setPhase(1), 700), setTimeout(() => setPhase(2), 2100)];
    return () => ts.forEach(clearTimeout);
  }, [ix, run, calc]);

  useEffect(() => {
    if (phase !== 2) return;
    if (typed >= calc.length) {
      const timer = setTimeout(() => setPhase(3), 380);
      return () => clearTimeout(timer);
    }
    const timer = setTimeout(() => setTyped((n) => n + 1), 22);
    return () => clearTimeout(timer);
  }, [phase, typed, calc.length]);

  function tilt(e: React.PointerEvent) {
    const el = wrap.current;
    if (!el || e.pointerType !== "mouse") return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--ry", `${((e.clientX - r.left) / r.width - 0.5) * 7}deg`);
    el.style.setProperty("--rx", `${-((e.clientY - r.top) / r.height - 0.5) * 7}deg`);
  }
  function untilt() {
    wrap.current?.style.setProperty("--ry", "0deg");
    wrap.current?.style.setProperty("--rx", "0deg");
  }

  return (
    <div className="demo">
      <div className="demo-stage" ref={wrap} onPointerMove={tilt} onPointerLeave={untilt}>
        <article className={`sheet demo-sheet phase-${phase}`} key={`${ix}-${run}`} aria-label={t("hero.aria", { vendor: ex.vendor })}>
          <header className="sheet-head">
            <div>
              <div className="sheet-vendor">{ex.vendor}</div>
              <div className="sheet-no fig">{t("hero.invoice", { no: ex.no })}</div>
            </div>
          </header>
          <dl className="sheet-rows">
            {rows.map(([k, v, fig], i) => (
              <div
                key={i}
                className={`sheet-row${phase >= 2 && i === ex.focus ? " is-focus" : ""}`}
                style={{ animationDelay: `${i * 90}ms` }}
              >
                <dt>{k}</dt>
                <dd className={fig ? "fig" : undefined}>{v}</dd>
              </div>
            ))}
          </dl>
          <div className="sheet-calc fig" aria-live="polite">
            {phase >= 2 && (
              <>
                {ex.rule && <span className="calc-rule">{ex.rule}</span>}
                {calc.slice(0, typed)}
                {phase === 2 && <span className="caret" aria-hidden />}
              </>
            )}
          </div>
          {phase === 1 && <div className="beam" aria-hidden />}
          {phase === 3 && (
            <div className="demo-stamp">
              <Stamp kind={ex.verdict} size="lg" />
            </div>
          )}
        </article>
      </div>
      <div className="demo-tabs" role="tablist" aria-label={t("hero.examples")}>
        {EXAMPLES.map((e, i) => (
          <button
            key={e.n}
            role="tab"
            aria-selected={i === ix}
            className={`demo-tab${i === ix ? " is-on" : ""}`}
            onClick={() => {
              setIx(i);
              setRun((n) => n + 1);
            }}
          >
            {t(`hero.t${e.n}`)}
          </button>
        ))}
      </div>
    </div>
  );
}
