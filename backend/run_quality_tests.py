"""
Quality-test runner.

  python run_quality_tests.py --provider offline   # no key: tests rules engine + API pipeline
  python run_quality_tests.py                      # live LLM from .env (runs ALL cases incl. llm_only)

Scoring is strict: a case passes only if BOTH the status and the exact set of
cited rule IDs match. Writes quality_test_report.md and quality_test_results.json.
"""
import argparse
import json
import os
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import baseline_naive  # noqa: E402
import llm_providers  # noqa: E402
import rules_engine  # noqa: E402

BASE = Path(__file__).parent
POLICY = json.loads((BASE / "policy.json").read_text(encoding="utf-8"))
CASES = json.loads((BASE / "test_cases.json").read_text(encoding="utf-8"))


def run(provider: str):
    rows = []
    for i, c in enumerate(CASES, 1):
        text = (BASE / c["file"]).read_text(encoding="utf-8")
        row = {"case": c, "error": None, "skipped": False}
        if provider == "offline" and c["llm_only"]:
            row["skipped"] = True
            rows.append(row)
            print(f"[{i:2d}/{len(CASES)}] {c['id']:<34} SKIP (needs a real LLM)")
            continue
        t0 = time.perf_counter()
        try:
            rec, usage, _ = llm_providers.extract_invoice(text=text, provider=provider)
            res = rules_engine.evaluate(POLICY, rec)
            row.update(actual_status=res["status"], actual_rules=sorted(v["rule_id"] for v in res["violations"]),
                       usage=usage, ms=int((time.perf_counter() - t0) * 1000), notes=res["notes"])
        except Exception as e:  # noqa: BLE001
            row["error"] = str(e)
        if not c["llm_only"]:
            bs, br = baseline_naive.naive_status(text)
            row.update(base_status=bs, base_rules=sorted(br))
        if row["error"]:
            print(f"[{i:2d}/{len(CASES)}] {c['id']:<34} ERROR {row['error'][:60]}")
        else:
            ok = row["actual_status"] == c["expected_status"] and row["actual_rules"] == sorted(c["expected_rule_ids"])
            row["ok"] = ok
            print(f"[{i:2d}/{len(CASES)}] {c['id']:<34} {'PASS' if ok else 'FAIL'}")
        rows.append(row)
        if provider != "offline":
            time.sleep(1.2)
    return rows


def report(rows, provider):
    ran = [r for r in rows if not r["skipped"]]
    passed = [r for r in ran if r.get("ok")]
    det = [r for r in ran if not r["case"]["llm_only"]]
    b_ok = [r for r in det if r["base_status"] == r["case"]["expected_status"]
            and r["base_rules"] == sorted(r["case"]["expected_rule_ids"])]
    b_stat = [r for r in det if r["base_status"] == r["case"]["expected_status"]]
    viol = [r for r in det if r["case"]["expected_rule_ids"]]
    found = sum(len(set(r["base_rules"]) & set(r["case"]["expected_rule_ids"])) for r in viol)
    total_exp = sum(len(r["case"]["expected_rule_ids"]) for r in viol)
    L = [f"# Quality Test Report ({provider} extraction)", "",
         f"Policy {POLICY['policy_version']} · {len(CASES)} cases defined · {len(ran)} run · "
         f"{len(rows) - len(ran)} skipped (need a live LLM)", "",
         f"**Strict pass (status AND exact rule IDs): {len(passed)}/{len(ran)}**", ""]
    if det:
        L += ["## Comparison with the current approach (amount-threshold filter)", "",
              "| Method | Exact pass (status + rules) | Status only | Violations correctly cited |",
              "|---|---|---|---|",
              f"| Amount-threshold filter (spreadsheet-style baseline) | {len(b_ok)}/{len(det)} | {len(b_stat)}/{len(det)} | {found}/{total_exp} |",
              f"| Ledger (extraction + rules engine) | {sum(1 for r in det if r.get('ok'))}/{len(det)} | "
              f"{sum(1 for r in det if r.get('actual_status') == r['case']['expected_status'])}/{len(det)} | "
              f"{sum(len(set(r['actual_rules']) & set(r['case']['expected_rule_ids'])) for r in viol if not r['error'])}/{total_exp} |",
              "", "The baseline checks only raw totals against category limits. It cannot divide by people or nights, "
              "check the vendor list, read approvals, handle currency or missing fields.", ""]
    ms = [r["ms"] for r in ran if "ms" in r]
    toks_in = sum(r["usage"]["input_tokens"] for r in ran if "usage" in r)
    toks_out = sum(r["usage"]["output_tokens"] for r in ran if "usage" in r)
    L += ["## Cost and speed", "",
          f"- Median latency per invoice: {statistics.median(ms)} ms" if ms else "- n/a",
          f"- Tokens over {len(ran)} cases: {toks_in} in / {toks_out} out"]
    cost = llm_providers.estimate_cost({"input_tokens": toks_in, "output_tokens": toks_out})
    if provider != "offline":
        L.append(f"- Estimated cost: ${cost:.4f} total, ${cost / max(len(ran), 1):.5f} per invoice" if cost is not None
                 else "- Set PRICE_IN_PER_MTOK / PRICE_OUT_PER_MTOK in .env to see cost per invoice.")
    L += ["", "## Per-case results", "",
          "| # | Case | What it tests | Expected | Actual | Result |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        c = r["case"]
        exp = f"{c['expected_status']} {c['expected_rule_ids'] or ''}"
        if r["skipped"]:
            L.append(f"| {i} | `{c['id']}` | {c['tests']} | {exp} | — | ⏭ needs LLM |")
        elif r["error"]:
            L.append(f"| {i} | `{c['id']}` | {c['tests']} | {exp} | ERROR | ⚠️ |")
        else:
            L.append(f"| {i} | `{c['id']}` | {c['tests']} | {exp} | {r['actual_status']} {r['actual_rules'] or ''} | "
                     f"{'✅' if r['ok'] else '❌'} |")
    L += ["", "## Failures", ""]
    bad = [r for r in ran if not r.get("ok")]
    if not bad:
        L.append("None in this run.")
    for r in bad:
        c = r["case"]
        L.append(f"- `{c['id']}`: expected {c['expected_status']} {c['expected_rule_ids']}; "
                 + (f"error: {r['error']}" if r["error"] else f"got {r['actual_status']} {r['actual_rules']}. {r['notes']}"))
    (BASE / "quality_test_report.md").write_text("\n".join(L), encoding="utf-8")
    (BASE / "quality_test_results.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k != "case"} | {"id": r["case"]["id"]} for r in rows], indent=2), encoding="utf-8")
    print(f"\n{len(passed)}/{len(ran)} strict pass. Report: quality_test_report.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=os.environ.get("LLM_PROVIDER", "gemini"))
    a = ap.parse_args()
    report(run(a.provider), a.provider)
