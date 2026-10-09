# Quality testing

## What was tested
- **42 cases** (`backend/test_cases.json`): 36 template-format cases and 6 free-text cases that need a real LLM
  (email prose, Azerbaijani receipt, Russian invoice, multi-line items with no printed total, vendor typo, prompt injection).
- Coverage: clean approvals, single and multiple violations, exact boundaries (150/151, 500, 2000), per-night
  division, per-person division, approval hierarchy (wrong approver level), Director/Finance-Director waivers,
  USD/EUR conversion at the fixed rates (incl. a converted amount landing exactly on a tier boundary and a
  USD total that only breaks a threshold after conversion), a currency with no rate, missing date, illegible amount, uncovered category, prompt injection.
- **Strict scoring:** pass = correct status **and** exactly the expected rule IDs.
- Plus 67 unit/regression/API tests (`backend/tests`): rules engine, currency conversion, approval guard, offline
  parsers, audit log, split warnings, the submission → alert → decision flow, **accounts and roles** (every
  private endpoint refused without a session, each role limited to its own pages, auditor requests approved or
  declined by the admin, exactly one admin, passwords and session tokens not stored in the clear), **duplicate
  refusal** (same file, same invoice in another file, no false positives on different invoices, caught before the
  model is called), the **decision history** (notes hidden from the employee, one decision at a time, reopening needs
  a reason), search, the per-person spending report, the overview totals and the CSV export.

## Results

### Rules engine + pipeline (reproducible, no key) — measured
`python run_quality_tests.py --provider offline` → **36/36 strict pass**; `pytest` → 67/67
(full table: `QUALITY_TEST_REPORT_OFFLINE.md`).

> Read this correctly: the offline run uses a regex extractor on the template format, so it proves the
> **decision logic** is correct and deterministic. It does **not** measure LLM extraction accuracy.

### Comparison with the current approach — measured
A spreadsheet-style filter (raw total vs. category limit, flat 2000 cap) on the same 36 cases:

| Method | Exact pass | Status only | Violations correctly cited |
|---|---|---|---|
| Amount-threshold filter | 14/36 | 21/36 | 16/29 |
| Ledger | 36/36 | 36/36 | 29/29 |

The filter cannot divide by people/nights, check the vendor list, read approvals, convert currency or notice missing data.
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

13. **Foreign currency was a dead end.** Every USD or EUR invoice went to a person, although the company has fixed
    rates. The engine now converts at the policy rates before any rule runs and shows the conversion in the trace.
    Case 17 changed from `needs_review` to `flagged EXP-1.1` (180 USD = 306 AZN for one person); cases 32–36 added.
    The split-purchase warning compared raw amounts with AZN tiers; it now compares converted values.
14. **Duplicates were only a warning.** The same PDF could be submitted twice and both copies approved. Uploads are
    now refused (same file, same vendor + invoice number, or same vendor + amount + currency + date); the extractor
    reads the invoice number for this.
15. **The audit desk was behind one shared PIN**, and the reviewer's name was typed by hand, so a decision could be
    recorded under any name. Replaced by accounts with roles; the decision is recorded under the signed-in auditor,
    and an auditor cannot decide on their own invoice.
16. **Self-registration as auditor lets anyone who can reach the sign-up page approve invoices.** Found while adding
    registration. The product owner chose immediate auditor access for this internal tool; the admin-approval flow is
    built, tested and one setting away (`AUDITOR_SIGNUP=approval`).
17. **A second auditor could overwrite a decision without a trace.** `decide` simply replaced the row. Now a decided
    invoice has to be reopened with a reason, and every step is kept in an append-only history.

## Known limits
Approval claims are checked against the document text, not against the approver's email or signature; one policy;
fixed exchange rates for USD and EUR only; content-based duplicate detection depends on what the extractor read; scanned-document accuracy depends on the vision model;
synthetic data only.

## Still to fill in (needs you)
- Live-LLM results (above).
- A real manual baseline: have 2–3 people check 10 of the invoices by hand and record time and errors in
  `manual_baseline_template.csv`, then quote the measured average.
