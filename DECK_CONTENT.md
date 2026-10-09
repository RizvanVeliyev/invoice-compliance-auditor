# Pitch deck content (slide by slide, mapped to the scoring card)

1. **Title** — Ledger: every invoice checked against policy, every flag with the rule and the maths.
2. **The user and the problem (Value 25)** — Accounts-payable / finance reviewer at a mid-size company. Today: open the policy PDF,
   compare by hand, do per-night/per-person division in their head, miss approvals. *Add one measured number: minutes per invoice from your manual baseline.*
3. **The outcome** — Verdict in seconds: approved / flagged / needs human. Each flag = rule ID + calculation + required approver.
4. **Live core scenario (Prototype 30)** — employee drops a hotel invoice PDF on /submit → stamped *Flagged* receipt with `1140 / 3 nights = 380 vs 300` → alert slides into the auditor's desk → auditor opens the PDF and rejects with a comment. Show both windows side by side. Link to demo + 2-minute video.
5. **What AI actually does (Prototype 30)** — Reads messy input: emails, Azerbaijani/Russian receipts, PDFs, photos, itemised totals. The code decides: exact maths, no prompt-injection power. Show the architecture diagram from the README.
6. **Quality testing (20)** — 37 cases, strict scoring (status + exact rules), boundary pairs, injection and forged-approval tests. 31/31 on the engine, baseline filter 11/31. **Live-LLM numbers from your run.** Show the failures/fixes honestly (incl. the forged-approval hole found and closed).
7. **Feasibility (15)** — Data needed: the company's policy as JSON + invoices. Cost per invoice (from your run: tokens × price). Audit log in SQLite, Docker one-command run. Next step: 1C/QuickBooks connector, approval verification via email/ERP, per-company policy editor.
8. **Originality (10)** — Rule engine separated from the LLM (auditable + injection-resistant), approval claims verified by code against the document, duplicate/split-purchase warnings, `needs_review` instead of guessing, calculation trace for auditors.
9. **Disclosure + limits** — models, data, components; known limits slide.
