# Quality testing

Last run: 9 October 2026, on the code in this repository (policy v2.5).

## Results at a glance
| What | How to run it | Result |
|---|---|---|
| Automated tests (API, engine, accounts, duplicates, reports, assistant, email) | `cd backend && python -m pytest -q tests` | **77 / 77 pass** |
| Quality cases, strict scoring, offline reader | `python run_quality_tests.py --provider offline` | **36 / 36 pass** (6 more need a live LLM) |
| Same 36 cases, spreadsheet-style amount filter | printed by the same runner | 14 / 36 |
| Frontend type check | `cd frontend && npx tsc --noEmit` | clean |
| Frontend production build | `npm run build` | 13 pages built, no errors |
| Translations | every key used in the code exists in all three languages | 447 entries, none missing, placeholders match |
| Email notification, real delivery | one decision sent through Gmail SMTP to the developer's own address | accepted by the mail server |
| Browser run (three roles, three languages, both themes, phone width) | scripted with a headless browser | no console errors, no horizontal overflow |
| Fresh-clone run, as a teammate would | clean clone, copied `.env.example` | starts, admin setup works, sample invoice judged correctly |
| Live model, the 6 free-text cases | `python run_quality_tests.py --only-llm --suffix _live` (gemini-3.6-flash) | **6 / 6 pass**, median 5.5 s, $0.00102 per invoice |
| Live model, template cases | `python run_quality_tests.py` (gemini-3.8-flash) | **7 / 7 pass** of the 7 that ran; 29 not run (free-tier quota of 20 requests a day) |
| Docker build | `docker compose up --build` | **not verified** (Docker would not start on the test machine) |
| Manual baseline (people checking invoices by hand) | `manual_baseline_template.csv` | **not measured yet** |

## What was tested

### Quality cases: does FiscalAI reach the right verdict, for the right reason?
- **42 cases** in `backend/test_cases.json`: 36 template-format cases and 6 free-text cases that need a real LLM
  (email prose, Azerbaijani receipt, Russian invoice, multi-line items with no printed total, vendor typo,
  prompt injection in free text).
- **Strict scoring:** a case passes only if the status is right **and** the cited rule IDs are exactly the expected set.
- Coverage: clean approvals; single and multiple violations; exact boundaries (150 / 151, 500, 2000);
  per-night and per-person division; the approval hierarchy (wrong approver level); Director and Finance
  Director waivers; **USD and EUR conversion** at the fixed rates, including a converted amount landing exactly
  on a tier boundary (1000 EUR = 2000 AZN) and a USD total that only breaks a threshold after conversion
  ($650 = 1105 AZN); a currency with no rate (GBP); missing date; illegible amount; a credit note; European
  number format; an uncovered category; pending approvals; prompt injection and a forged approval line.
- Full per-case table: `QUALITY_TEST_REPORT_OFFLINE.md`.

> Read this correctly: the offline run uses a regex reader on the template format, so it proves the
> **decision logic** is correct and deterministic. It does **not** measure how well a model reads messy documents.

### Comparison with the current approach
A spreadsheet-style filter (raw total against the category limit, flat 2000 cap) on the same 36 cases:

| Method | Exact pass | Status only | Violations correctly cited |
|---|---|---|---|
| Amount-threshold filter | 14/36 | 21/36 | 16/29 |
| FiscalAI | 36/36 | 36/36 | 29/29 |

The filter cannot divide by people or nights, check the vendor list, read approvals, convert currency or notice
missing data. It is a proxy for "how this is done today", not a measurement of human reviewers.

### Automated tests: does the product around the verdict behave?
77 tests in `backend/tests`:

| File | Tests | What they pin down |
|---|---|---|
| `test_rules_engine.py` | 12 | limits and boundaries, division, waivers, tiers, currency conversion at 1.7 and 2.0, a currency without a rate, injected values cannot change the verdict |
| `test_review_fixes.py` | 17 | one regression test per defect found in review: forged approvals, flights judged as hotels, the offline approval parser, zero / negative / missing amounts, number formats, policy-driven waivers, audit-log failures, split-purchase warnings |
| `test_auth.py` | 16 | nothing private without a session; each role limited to its own endpoints; one admin, never by registration or promotion; open and admin-approved auditor sign-up; passwords and session tokens not stored in the clear; lock after repeated wrong passwords; sign-out and deactivation end the session; nobody decides on their own invoice |
| `test_submissions.py` | 16 | upload → verdict → alert → decision; scanned and fake files; USD and EUR invoices; the submitter's currency choice; **duplicates refused** (same file, same invoice in another file, caught before the model is called, no false positives, resubmission after rejection); the employee's own list; overview totals; CSV export with formula-safe cells |
| `test_assistant.py` | 8 | the assistant: policy answers in three languages; planned expenses judged by the real engine (conversion, per-night and per-person maths, tiers); budgets in every currency; tips for fitting a limit; verdict tone and next-step links; **an employee cannot ask about a colleague's invoice or get company-wide rankings**; the fallback, the model hand-off and the rate limit |
| `test_mail.py` | 2 | the employee is emailed on clear and on reject, with the right content, and not for notes or reopening; a missing or broken mail server never blocks a decision |
| `test_audit_tools.py` | 6 | the decision history, internal notes hidden from the employee, one decision at a time, reopening needs a reason; search; **filters and paging** with the total count; the per-person spending report; the audit team's list of people |

### Checked in a real browser
A scripted headless browser registered an employee, signed in as the auditor and the admin, uploaded the
samples, rejected, added a note, reopened and cleared invoices, and opened every page in Azerbaijani, English
and Russian, in the light and the dark theme, at desktop and phone width. With 35 invoices and 17 accounts
seeded, paging and each filter returned the expected rows (for example the currency filter left only USD
invoices; currency plus search left two). No console errors and no horizontal overflow at 390 px.

The assistant was exercised the same way: opened from the corner button, asked by typing, by topic card and by
suggestion chip in Azerbaijani, English and Russian; verdict badges and action links appeared as expected, the
conversation survived a reload, Esc closed the panel, and on a phone it opened full screen without overflow.

### Live model
13 of 42 cases were run against a live model and **13 / 13 passed**: all 6 free-text cases (email prose, Azerbaijani receipt, Russian invoice, itemised total, vendor typo, prompt injection) on `gemini-3.6-flash`, and 7 template cases on `gemini-3.8-flash`.

| | |
|---|---|
| Strict pass on what ran | 13 / 13 |
| Median time per invoice (6 free-text cases) | 5.5 s (fastest 3.3 s, slowest 28.9 s) |
| Tokens per invoice | about 820 in, 110 out |
| Cost per invoice | $0.00102, about **$1.02 per 1,000 invoices** (gemini-3.6-flash at $0.75 / $3.75 per million tokens) |
| Full table | `QUALITY_TEST_REPORT_LIVE.md` |

What this does and does not show: the free-text cases are the ones a regex reader cannot do at all, and the model
read every one correctly, including Azerbaijani and Russian, a total that had to be added up, and an injected
instruction that had to be ignored. **29 template cases were not run live**: the first full run stopped after 7
cases when the free tier's limit of 20 requests a day for that model was used up, so there is no live result for
them, good or bad. The numbers come from 13 synthetic invoices and two model versions, which is a small sample.
Scanned images were tried by hand in the app, not in this scored run.

## Not measured yet
- **The 29 template cases against a live model**, and any live run on scanned images. Both need a key with a
  larger quota.
- **The assistant's model hand-off.** Questions the code does not recognise go to a model when one is configured;
  that path is covered only with a stubbed model, never a real key.
- **A manual baseline.** Have 2–3 people check 10 of the invoices by hand and record time and errors in
  `manual_baseline_template.csv`; that gives the "minutes per invoice today" number the comparison lacks.
- **The Docker build.** The Dockerfiles need no change for the new code (no new dependencies), but the build
  itself was not run.
- **Load.** Nothing was tested with thousands of invoices or many people at once.

## Failures found and fixed during development
1. **Wrong test expectation.** Case 14 (1500 AZN software, no approval) expected only EXP-2.1, but EXP-4.1 (500–2000 needs
   Manager) also applies, exactly as in cases 04 and 09. The old runner compared only `status`, so it never noticed.
   Fixed the expectation and made the runner compare rule IDs.
2. **LLM doing arithmetic and judgment.** The first version asked the model to divide totals by nights/people and to decide
   compliance. That is non-reproducible and open to prompt injection. Replaced with extraction-only LLM + deterministic engine.
3. **Spec conflict surfaced while coding the engine.** "Uncovered category → needs_review" (case 06) contradicted case 18
   (uncovered category with documented Finance Director approval → approved). Resolved with an explicit policy rule: an
   uncovered category is cleared only when its amount tier requires approval and that approval is documented.
4. **Tier boundaries were undefined** (500 and 2000). Now explicit in `policy.json` and covered by cases 20–21.
5. **Leaked credential.** A live API key was shipped inside an early project zip. Removed; `.env` is git- and
   docker-ignored; the key must be revoked.
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
   credit notes (found by case 30: a −240 refund was flagged as a 240 meal). All fixed; cases 30–31.
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
18. **Searching `#1` returned unrelated invoices.** The digit also matched inside invoice numbers such as
    `PF-2026-031`. A `#id` search is now exact; found by the search test.
19. **Dates showed as "2026 M10 9" in Azerbaijani.** Browsers often ship without Azerbaijani month names. Month
    names for all three languages are now in the app; found in the browser run.
20. **Layout overflow.** Long rule descriptions pushed the "rules broken" card past its edge and made the overview
    scroll sideways on a phone (906 px too wide). Fixed; the browser run now checks overflow at 390 px.
21. **The copied `.env.example` broke a fresh install.** It selected a model that needs an API key, so every upload
    failed to read. It now defaults to the offline reader; found by the fresh-clone run.

22. **The assistant did not recognise "ПО".** The Russian abbreviation for software fell through to "other
    expense", so "ПО 650 USD" missed the IT-approval rule. Found in the browser run; added with a test.
23. **"Approved vendors" also printed the approval tiers**, because the Azerbaijani word for "approved" contains
    the word for "approval". A vendor question now answers only about vendors.
24. **An assistant test expected the wrong number.** It assumed the over-limit hotel sample also lacked Manager
    approval; the sample has it, so EXP-4.1 fires once, not twice. The expectation was wrong, not the engine.

25. **The full live run burned its quota on retries.** The model answered "busy" (503) often; our new retry
    waited and tried again, and each attempt counted against a free-tier limit of 20 requests a day that we did
    not know about. 7 cases completed, then every call failed with "quota exceeded" and the runner still waited
    through three retries each, for over an hour. Fix: a used-up quota is no longer retried, the runner can run
    only the cases that need a model (`--only-llm`), and a live run writes its own report instead of replacing
    the offline one. The 35 quota errors were never counted as model failures.
26. **Category words were English only.** A model reporting "otel" or "отель" would not have matched the hotel
    rule. Azerbaijani and Russian words were added to `policy.json` before the live run.

## Known limits
Approval claims are checked against the document text, not against the approver's email or signature; one policy;
fixed exchange rates for USD and EUR only; content-based duplicate detection depends on what the extractor read;
scanned-document accuracy depends on the vision model; the sentences the engine writes about an invoice are in
English in every interface language; without a model the assistant covers a fixed set of topics; synthetic data only.
