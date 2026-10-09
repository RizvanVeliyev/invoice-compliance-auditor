"use client";

import { useEffect, useRef, useState } from "react";
import Stamp from "./Stamp";

type Example = {
  tab: string;
  vendor: string;
  no: string;
  rows: [string, string][];
  focus: number; // index of the row the check is about
  calc: string;
  verdict: "approved" | "flagged" | "needs_review";
  rule: string;
};

const EXAMPLES: Example[] = [
  {
    tab: "Hotel, 3 nights",
    vendor: "Baku Business Hotel",
    no: "BBH-88310",
    rows: [
      ["Employee", "Murad Quliyev"],
      ["Category", "Travel - Accommodation"],
      ["Description", "Executive room, 3 nights"],
      ["Amount", "1,140.00 AZN"],
      ["Approval", "Manager Rauf Ismayilov"],
    ],
    focus: 3,
    calc: "1140 / 3 nights = 380 per night; limit 300",
    verdict: "flagged",
    rule: "EXP-1.2",
  },
  {
    tab: "Client lunch",
    vendor: "City Catering Group",
    no: "CCG-24117",
    rows: [
      ["Employee", "Aysel Karimova"],
      ["Category", "Meals & Entertainment"],
      ["Description", "Lunch with 2 clients"],
      ["Amount", "390.00 AZN"],
      ["Approval", "Not needed under 500"],
    ],
    focus: 3,
    calc: "390 / 3 people = 130 per person; limit 150",
    verdict: "approved",
    rule: "EXP-1.1",
  },
  {
    tab: "Office monitor",
    vendor: "Caspian Office Supplies",
    no: "COS-7702",
    rows: [
      ["Employee", "Tural Ismayilov"],
      ["Category", "Office Equipment"],
      ["Description", "Replacement monitor"],
      ["Amount", "410.00 AZN"],
      ["Approval", "None stated"],
    ],
    focus: 1,
    calc: "No policy rule covers office equipment; sent to a person",
    verdict: "needs_review",
    rule: "",
  },
];

// phase: 0 ink, 1 scanning, 2 calculation, 3 stamped
export default function HeroDemo() {
  const [ix, setIx] = useState(0);
  const [run, setRun] = useState(0);
  const [phase, setPhase] = useState(0);
  const [typed, setTyped] = useState(0);
  const wrap = useRef<HTMLDivElement>(null);
  const ex = EXAMPLES[ix];

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setPhase(3);
      setTyped(ex.calc.length);
      return;
    }
    setPhase(0);
    setTyped(0);
    const ts = [
      setTimeout(() => setPhase(1), 700),
      setTimeout(() => setPhase(2), 2100),
    ];
    return () => ts.forEach(clearTimeout);
  }, [ix, run, ex.calc.length]);

  useEffect(() => {
    if (phase !== 2) return;
    if (typed >= ex.calc.length) {
      const t = setTimeout(() => setPhase(3), 380);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setTyped((n) => n + 1), 22);
    return () => clearTimeout(t);
  }, [phase, typed, ex.calc.length]);

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
        <article className={`sheet demo-sheet phase-${phase}`} key={`${ix}-${run}`} aria-label={`Example invoice from ${ex.vendor}`}>
          <header className="sheet-head">
            <div>
              <div className="sheet-vendor">{ex.vendor}</div>
              <div className="sheet-no fig">Invoice {ex.no}</div>
            </div>
          </header>
          <dl className="sheet-rows">
            {ex.rows.map(([k, v], i) => (
              <div
                key={k}
                className={`sheet-row${phase >= 2 && i === ex.focus ? " is-focus" : ""}`}
                style={{ animationDelay: `${i * 90}ms` }}
              >
                <dt>{k}</dt>
                <dd className={k === "Amount" ? "fig" : undefined}>{v}</dd>
              </div>
            ))}
          </dl>
          <div className="sheet-calc fig" aria-live="polite">
            {phase >= 2 && (
              <>
                {ex.rule && <span className="calc-rule">{ex.rule}</span>}
                {ex.calc.slice(0, typed)}
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
      <div className="demo-tabs" role="tablist" aria-label="Example invoices">
        {EXAMPLES.map((e, i) => (
          <button
            key={e.tab}
            role="tab"
            aria-selected={i === ix}
            className={`demo-tab${i === ix ? " is-on" : ""}`}
            onClick={() => {
              setIx(i);
              setRun((n) => n + 1);
            }}
          >
            {e.tab}
          </button>
        ))}
      </div>
    </div>
  );
}
