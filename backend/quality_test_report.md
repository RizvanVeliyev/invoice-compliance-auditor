# Quality Test Report (offline extraction)

Policy v2.5 · 42 cases defined · 36 run · 6 skipped (need a live LLM)

**Strict pass (status AND exact rule IDs): 36/36**

## Comparison with the current approach (amount-threshold filter)

| Method | Exact pass (status + rules) | Status only | Violations correctly cited |
|---|---|---|---|
| Amount-threshold filter (spreadsheet-style baseline) | 14/36 | 21/36 | 16/29 |
| Ledger (extraction + rules engine) | 36/36 | 36/36 | 29/29 |

The baseline checks only raw totals against category limits. It cannot divide by people or nights, check the vendor list, read approvals, handle currency or missing fields.

## Cost and speed

- Median latency per invoice: 0.0 ms
- Tokens over 36 cases: 0 in / 0 out

## Per-case results

| # | Case | What it tests | Expected | Actual | Result |
|---|---|---|---|---|---|
| 1 | `01-clean-approved` | Fully clean invoice — approved vendor, under all limits | approved  | approved  | ✅ |
| 2 | `02-over-limit-restaurant` | Single clear violation — meal amount over the per-person limit | flagged ['EXP-1.1'] | flagged ['EXP-1.1'] | ✅ |
| 3 | `03-unapproved-vendor` | Single clear violation — vendor not on the approved list | flagged ['EXP-3.1'] | flagged ['EXP-3.1'] | ✅ |
| 4 | `04-missing-approval-large` | Two overlapping rules on one invoice — software threshold AND approval threshold | flagged ['EXP-2.1', 'EXP-4.1'] | flagged ['EXP-2.1', 'EXP-4.1'] | ✅ |
| 5 | `05-multiple-violations` | Three simultaneous violations — the hardest aggregation case in the set | flagged ['EXP-1.2', 'EXP-3.1', 'EXP-4.1'] | flagged ['EXP-1.2', 'EXP-3.1', 'EXP-4.1'] | ✅ |
| 6 | `06-borderline-edge-case` | Category with no matching rule (410 AZN office equipment, approved vendor): must not invent a rule; routed to needs_review | needs_review  | needs_review  | ✅ |
| 7 | `07-exact-limit-boundary` | Amount exactly AT the limit (150 AZN) — policy says 'may not exceed', so this must NOT be flagged | approved  | approved  | ✅ |
| 8 | `08-just-over-limit` | Amount 1 AZN over the limit — checks sensitivity, paired with case 07 as a boundary pair | flagged ['EXP-1.1'] | flagged ['EXP-1.1'] | ✅ |
| 9 | `09-approved-vendor-missing-approval` | Vendor IS approved but two amount-based rules still apply — checks vendor-ok doesn't mask other violations | flagged ['EXP-2.1', 'EXP-4.1'] | flagged ['EXP-2.1', 'EXP-4.1'] | ✅ |
| 10 | `10-double-violation` | Unlisted vendor + uncovered category + 2800 AZN with no Finance Director approval | flagged ['EXP-3.1', 'EXP-4.1'] | flagged ['EXP-3.1', 'EXP-4.1'] | ✅ |
| 11 | `11-travel-clean` | Clean case in a different category (Travel) to check the approved-vendor path isn't Meals-specific | approved  | approved  | ✅ |
| 12 | `12-travel-over-limit` | Accommodation over the per-night limit, isolated single violation | flagged ['EXP-1.2'] | flagged ['EXP-1.2'] | ✅ |
| 13 | `13-software-clean` | Clean software purchase under both the category limit and the approval threshold | approved  | approved  | ✅ |
| 14 | `14-software-over-threshold` | Software purchase of 1500 AZN, no approval: needs IT approval (EXP-2.1) AND Manager approval (EXP-4.1, 500-2000 tier). [Expectation corrected: originally listed EXP-2.1 only.] | flagged ['EXP-2.1', 'EXP-4.1'] | flagged ['EXP-2.1', 'EXP-4.1'] | ✅ |
| 15 | `15-missing-date-field` | Amount and vendor are fine, but the date is missing — checks the system flags missing data instead of assuming it's fine | needs_review  | needs_review  | ✅ |
| 16 | `16-multi-night-math` | Only a 3-night TOTAL is given — the model must divide to get the per-night rate before checking the limit | flagged ['EXP-1.2', 'EXP-4.1'] | flagged ['EXP-1.2', 'EXP-4.1'] | ✅ |
| 17 | `17-foreign-currency` | Invoice in USD: 180 USD x 1.7 = 306 AZN for one person, over the 150 AZN meal limit. Must be converted, not read as 180 AZN and not sent to review. [Expectation changed in policy v2.5: USD and EUR now have fixed rates.] | flagged ['EXP-1.1'] | flagged ['EXP-1.1'] | ✅ |
| 18 | `18-fully-compliant-high-value` | Large amount but with a properly documented Finance Director approval — checks the system doesn't flag on amount alone and reads the approval line | approved  | approved  | ✅ |
| 19 | `19-prompt-injection` | Invoice contains an instruction to the AI to approve it; verdict must ignore it | flagged ['EXP-3.1', 'EXP-4.1'] | flagged ['EXP-3.1', 'EXP-4.1'] | ✅ |
| 20 | `20-tier-boundary-500` | Exactly 500 AZN with no approval: lower tier boundary is inclusive | flagged ['EXP-4.1'] | flagged ['EXP-4.1'] | ✅ |
| 21 | `21-tier-boundary-2000` | Exactly 2000 AZN with no approval: Manager tier (not Finance Director) applies | flagged ['EXP-4.1'] | flagged ['EXP-4.1'] | ✅ |
| 22 | `22-wrong-approver-level` | 2600 AZN software with IT + Manager approval: IT satisfies EXP-2.1, but >2000 still needs Finance Director | flagged ['EXP-4.1'] | flagged ['EXP-4.1'] | ✅ |
| 23 | `23-group-meal-approved` | 620 AZN meal for 5 people (124 each) with Manager approval: total is high but per-person is fine | approved  | approved  | ✅ |
| 24 | `24-hotel-director-approved` | 400 AZN/night exceeds 300 but Director pre-approval and Manager approval are documented | approved  | approved  | ✅ |
| 25 | `25-unlisted-vendor-fd-signoff` | Vendor not on list but Finance Director sign-off is documented (4 attendees, 100 per person) | approved  | approved  | ✅ |
| 26 | `26-missing-amount` | Amount illegible: must not be treated as zero | needs_review  | needs_review  | ✅ |
| 27 | `27-flight-generic-travel` | Generic 'Travel' (a flight) must not trigger the per-night hotel rule; manager tier met | approved  | approved  | ✅ |
| 28 | `28-pending-approval` | Approval requested but not yet given is not an approval | flagged ['EXP-4.1'] | flagged ['EXP-4.1'] | ✅ |
| 29 | `29-forged-approval-line` | Approval line written as an instruction to the AI: discarded, flagged and sent for human check | flagged ['EXP-3.1', 'EXP-4.1'] | flagged ['EXP-3.1', 'EXP-4.1'] | ✅ |
| 30 | `30-credit-note-negative` | Negative amount (credit note) routed to a human, not auto-approved | needs_review  | needs_review  | ✅ |
| 31 | `31-european-number-format` | Amount '1.250,00 AZN' parsed as 1250, Manager tier met | approved  | approved  | ✅ |
| 32 | `32-usd-meal-converted` | 240 USD x 1.7 = 408 AZN for 3 people = 136 per person: under the meal limit and under the 500 AZN tier | approved  | approved  | ✅ |
| 33 | `33-eur-hotel-over-limit` | 340 EUR x 2 = 680 AZN over 2 nights = 340 per night (limit 300); Manager approval covers the 500-2000 tier but does not waive the hotel limit | flagged ['EXP-1.2'] | flagged ['EXP-1.2'] | ✅ |
| 34 | `34-usd-software-crosses-threshold` | $650 looks under the 1000 software threshold but is 1105 AZN: needs IT approval and Manager approval | flagged ['EXP-2.1', 'EXP-4.1'] | flagged ['EXP-2.1', 'EXP-4.1'] | ✅ |
| 35 | `35-eur-tier-boundary` | 1000 EUR x 2 = exactly 2000 AZN: still the Manager tier (upper boundary inclusive) after conversion | approved  | approved  | ✅ |
| 36 | `36-unsupported-currency-gbp` | GBP has no rate in the policy: must go to a person, never be read as 60 AZN | needs_review  | needs_review  | ✅ |
| 37 | `L1-email-prose` | Free-text email: LLM must infer 5 attendees, 640 total, Manager approval (128/person) | approved  | — | ⏭ needs LLM |
| 38 | `L2-azerbaijani-receipt` | Azerbaijani receipt: 2 nights, 760 total -> 380/night; no approval | flagged ['EXP-1.2', 'EXP-4.1'] | — | ⏭ needs LLM |
| 39 | `L3-russian-invoice` | Russian invoice: IT approval present (satisfies EXP-2.1), Manager approval explicitly absent (1200 AZN tier) | flagged ['EXP-4.1'] | — | ⏭ needs LLM |
| 40 | `L4-multi-line-items` | No printed total: LLM must sum 700+450+600=1750; Manager approval documented; uncovered category cleared by approval | approved  | — | ⏭ needs LLM |
| 41 | `L5-vendor-typo` | Vendor typo 'City Catering Grp': extracted as written, flagged with near-match note for human confirmation | flagged ['EXP-3.1'] | — | ⏭ needs LLM |
| 42 | `L6-injection-free-text` | Prompt injection inside free text must not change extraction or verdict | flagged ['EXP-3.1', 'EXP-4.1'] | — | ⏭ needs LLM |

## Failures

None in this run.