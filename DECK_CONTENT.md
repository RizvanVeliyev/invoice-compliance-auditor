# Pitch deck content (slide by slide, mapped to the scoring card)

Numbers on these slides come from the run recorded in `QUALITY_TESTING.md`. Items in *italics* are still to
be measured; do not present them with invented figures.

## 1. Title
**FiscalAI: every invoice checked against policy before anyone pays it.**
Every flag names the rule and shows the maths.

## 2. The user and the problem — Value for the user (25)
- **Who:** the finance / audit team of a mid-size company, and every employee who files an expense.
- **Today:** the auditor opens the policy, compares each invoice by hand, divides totals by nights and guests
  in their head, converts dollars and euros, hunts for the approval line, and has no way to notice the same
  invoice arriving twice. The employee sends a PDF and hears nothing until it is paid or bounced.
- **What goes wrong:** over-limit hotels hidden in a multi-night total, a $650 purchase that is really
  1105 AZN, a missing approval, an unlisted vendor, a duplicate.
- *Add the measured number: minutes per invoice from the manual baseline (`manual_baseline_template.csv`).*

## 3. The outcome
- **Employee:** uploads a PDF or photo, gets a stamped answer in seconds (approved / flagged / needs review)
  with the reason, and follows the decision and their own spending per month.
- **Auditor:** sees only what needs a person, with the rule, the calculation and the original document side
  by side; clears or rejects in one click; every step is recorded.
- **Management:** totals in AZN, by currency, by rule, by employee; CSV export.
- **Everyone:** an assistant that answers "may I spend this?" before the money is spent, and an email the
  moment a decision is made.

## 4. Live core scenario — Prototype and use of AI (30)
Two windows side by side, employee and auditor:
1. Employee sends **Hotel over limit** → stamped *Flagged*: `1140 / 3 nights = 380 per night vs limit 300`.
   The alert slides into the audit desk.
2. Employee sends **Software in dollars** → `650 USD x 1.7 = 1105 AZN`: two rules broken that the raw
   number hides.
3. Employee sends the hotel invoice again → **Duplicate, not accepted**.
4. Employee sends **Forged approval note** → the instruction to the AI inside the PDF is reported and ignored.
5. Auditor opens the hotel alert, adds an internal note, rejects with a comment; the employee sees it on
   **My invoices**. Auditor reopens it with a reason: the history shows every step.
6. Open the assistant and ask "hotel 900 AZN 2 nights": it shows 450 per night against the 300 limit and
   how to fit it (at most 600 AZN). Ask "max for hotel, 3 nights": 900 AZN = 529.41 USD = 450 EUR.
7. Show the email the employee received about the rejection.
8. Switch the language (AZ / EN / RU) and the theme once, live.

Link to the repository and a 2-minute recording.

## 5. What the AI actually does — Prototype and use of AI (30)
- **The AI reads:** vendor, invoice number, amount, currency, dates, nights, guests and approval lines from
  PDFs, photos, emails and free text, in English, Azerbaijani or Russian.
- **The code decides:** limits, division, currency conversion, tiers and approvals are plain code driven by
  `policy.json`. Same input, same verdict, exact arithmetic.
- **Why it matters:** text inside an invoice cannot talk its way to "approved". Even an approval the model
  reports is kept only if code finds that sentence in the document.
- **The assistant follows the same rule:** its answers about limits and planned expenses are computed by the
  rules engine, not generated, so it works without a model and never contradicts a real verdict.
- Show the pipeline diagram from the README.

## 6. Quality testing (20)
- **36 / 36** quality cases pass with strict scoring (right status **and** exactly the right rule IDs):
  boundaries, per-night and per-person maths, approval hierarchy, USD/EUR conversion, missing data, prompt
  injection, forged approvals.
- **Comparison with the current approach:** a spreadsheet-style amount filter gets **14 / 36** on the same
  cases and cites 16 of 29 violations; FiscalAI cites 29 of 29.
- **79 / 79** automated tests: roles and sessions, duplicate refusal, decision history, filters and paging,
  reports, export, the assistant (including that an employee cannot ask about a colleague's invoice) and
  email notifications.
- **Examples of failures, shown honestly** (26 are listed in `QUALITY_TESTING.md`): a note saying
  "pre-cleared by the Finance Director" could once approve a 4800 AZN payment; a flight was judged as a
  900 AZN hotel night; a refund of −240 was flagged as a 240 AZN meal; a second auditor could overwrite a
  decision without a trace. Each one has a fix and a test.
- **Live model: 13 / 13** of the cases that ran: all 6 free-text cases (Azerbaijani, Russian, email, itemised
  total, vendor typo, prompt injection) on gemini-3.6-flash and 7 template cases on gemini-3.8-flash. Median
  5.5 s per invoice. 29 template cases were not run live: the free tier allows 20 requests a day.
- State plainly what the offline numbers prove (the decision logic) and what they do not (how well a model
  reads a messy scan).

## 7. Feasibility (15)
- **Data needed:** the company's expense policy as one JSON file (limits, tiers, vendors, rates) and the
  invoices themselves. No training data, no history.
- **Running cost:** one model call per invoice; a PDF with a text layer is read locally first, and a
  duplicate file is refused before any model call. Measured: $0.00102 per invoice, about **$1.02 per 1,000
  invoices** (gemini-3.6-flash).
- **Deployment:** two processes (FastAPI + Next.js) and a SQLite file; runs on one small server inside the
  company network. Any of three model providers, or none for template documents.
- **Clear next step:** pilot with one finance team on real invoices for two weeks, measuring time per invoice
  and missed violations against today's process. Then: company sign-on (SSO), a connector to the accounting
  system (1C / QuickBooks) for the approved invoices, approval verification against email or the ERP, and a
  policy editor so finance can change limits without a developer.

## 8. Originality (10)
- The rule engine is separated from the model: auditable, reproducible and injection-resistant, where most
  "AI checks your invoice" tools let the model give the verdict.
- Approval claims are verified by code against the document text.
- Duplicates are **refused at upload**, including the same invoice re-scanned into a different file.
- Fixed-rate currency conversion is part of the shown calculation, not a hidden step.
- "Needs review" instead of a guess whenever data is missing or the policy is silent.
- A policy assistant that **computes** instead of generating: "what if" answers come from the same engine as
  the real verdict, in three languages, with no model required.
- Separation of duties built in: nobody decides on their own invoice, a decision cannot be silently
  overwritten, and each invoice carries an append-only history.

## 9. What it is built with, and its limits
- **Models:** Google Gemini (gemini-3.6-flash in the demo and the free-text run; gemini-3.8-flash in the first
  run) reads invoices. Claude or GPT can be configured instead. The verdict is never produced by a model.
- **Data:** synthetic invoices and a fictional company policy. No real or personal data.
- **Components:** FastAPI, Pydantic, pypdf, SQLite, Next.js, React, TypeScript.
- **Limits:** the live run covers 13 of 42 cases; approvals are checked against the document, not
  against the approver's mailbox; fixed exchange rates for USD and EUR only; FiscalAI's own accounts rather
  than company sign-on; the engine's explanations are in English in every interface language.
