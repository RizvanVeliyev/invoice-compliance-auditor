# Quality testing

## What was tested
- **37 cases** (`backend/test_cases.json`): 31 template-format cases and 6 free-text cases that need a real LLM
  (email prose, Azerbaijani receipt, Russian invoice, multi-line items with no printed total, vendor typo, prompt injection).
- Coverage: clean approvals, single and multiple violations, exact boundaries (150/151, 500, 2000), per-night
  division, per-person division, approval hierarchy (wrong approver level), Director/Finance-Director waivers,
  foreign currency, missing date, illegible amount, uncovered category, prompt injection.
- **Strict scoring:** pass = correct status **and** exactly the expected rule IDs.
- Plus 35 unit/regression/API tests (`backend/tests`): rules engine, approval guard, offline parsers, audit log, duplicate/split warnings, and the employee PDF submission → alert → decision flow (incl. scanned PDF, fake-PDF upload, auditor PIN).

## Results

### Rules engine + pipeline (reproducible, no key) — measured
`python run_quality_tests.py --provider offline` → **31/31 strict pass**, 35/35 tests, API smoke test OK
(full table: `QUALITY_TEST_REPORT_OFFLINE.md`).

> Read this correctly: the offline run uses a regex extractor on the template format, so it proves the
> **decision logic** is correct and deterministic. It does **not** measure LLM extraction accuracy.

### Comparison with the current approach — measured
A spreadsheet-style filter (raw total vs. category limit, flat 2000 cap) on the same 31 cases:

| Method | Exact pass | Status only | Violations correctly cited |
|---|---|---|---|
| Amount-threshold filter | 11/31 | 18/31 | 14/25 |
| Ledger | 31/31 | 31/31 | 25/25 |

The filter cannot divide by people/nights, check the vendor list, read approvals, or handle currency and missing data.
This is a proxy baseline, not a measurement of human reviewers (see "Still to fill in").

### Live-LLM extraction — **fill in after running**
`cd backend && python run_quality_tests.py` (your provider) → paste the strict-pass count, the 6 free-text cases,
median latency and cost per invoice here. Do not submit this section blank or with invented numbers.

## Failures and fixes found during development
1. **Wrong test expectation.** Case 14 (1500 AZN software, no approval) expected only EXP-2.1, but EXP-4.1 (500–2000 needs
   Manager) also applies, exactly as in cases 04 and 09. The old runner compared only `status`, so it never noticed.
   Fixed the expectation and made the runner compare rule IDs.
2. **LLM doing arithmetic and judgment.** The first version asked the model to divide totals by nights/people and to decide
   compliance. That is non-reproducible and open to prompt injection. Replaced with extraction-only LLM + deterministic engine.
3. **Spec conflict surfaced while coding the engine.** "Uncovered category → needs_review" (case 06) contradicted case 18
   (uncovered category with documented Finance Director approval → approved). Resolved with an explicit policy rule: an
   uncovered category is cleared only when its amount tier requires approval and that approval is documented.
4. **Tier boundaries were undefined** (500 and 2000). Now explicit in `policy.json` and covered by cases 20–21.
5. **Leaked credential.** A live API key was shipped inside the project zip. Removed; `.env` is git/docker-ignored;
   the key must be revoked.

6. **Forged approvals via prompt injection.** The verdict was computed by code, but the `approvals` list it trusts came
   from the model reading the whole invoice, so "pre-cleared by the Finance Director" in a note could have approved a
   4800 AZN payment to an unlisted vendor. Added `approval_guard.py`: approvals are kept only if their quoted evidence is
   found in the document, is not pending/refused, and is not on a line addressed to an AI; reviewer-directed text forces
   human review. Cases 28–29 and 9 unit tests.
7. **Flights judged as hotels.** The alias `travel` mapped to *Travel - Accommodation*, so a 900 AZN flight was flagged
   as 900 AZN/night. Removed the alias; case 27.
8. **Offline approval parser.** "Manager approved it" was read as IT approval; "Pending manager approval" and "requested
   from Finance Director" were read as given. Now clause-by-clause with negation handling and upper-case `IT` only.
9. **Amounts.** Zero/negative amounts were auto-approved or mis-described; a missing amount was returned as 0 (UI showed
   "0 AZN"). The offline parser read `1.234,50` as 1.2345, lost the currency in `AZN 900`, and dropped the minus sign of
   credit notes (found by new case 30: a −240 refund was flagged as a 240 meal). All fixed; cases 30–31.
10. **Hard-coded policy values.** `waived_by` in `policy.json` was ignored and the 2000/500 limits were hard-coded in
    messages and severity. Now read from the policy.
11. **Silent audit failures.** A failed audit write was swallowed; now logged and shown (`meta.audit_logged`).
12. **Upload size.** The whole upload was read into memory before the 5 MB check; now reads at most limit+1 bytes.

## Known limits
Approval claims are read, not verified; one policy; no FX table; scanned-document accuracy depends on the vision model;
synthetic data only.

## Still to fill in (needs you)
- Live-LLM results (above).
- A real manual baseline: have 2–3 people check 10 of the invoices by hand and record time and errors in
  `manual_baseline_template.csv`, then quote the measured average.
