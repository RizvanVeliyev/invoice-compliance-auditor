"""
Deterministic policy engine.

The LLM never decides compliance. It only turns messy input (free text, other
languages, scans) into the structured record below. Every limit, threshold,
division and approval check is plain Python driven by policy.json, so the same
extraction always yields the same verdict, every number is reproducible, and a
prompt-injected invoice cannot talk its way to "approved".

Extracted record (see EXTRACTION_FIELDS):
    vendor, amount, currency, category, date, employee, description,
    nights, attendees, approvals (list of manager|it|director|finance_director),
    approval_evidence (verbatim text that supports the approvals)
"""

from __future__ import annotations

import difflib
import re
from typing import Any

EXTRACTION_FIELDS = [
    "vendor", "amount", "currency", "category", "date", "employee",
    "description", "nights", "attendees", "approvals", "approval_evidence",
]


# ---------------------------------------------------------------- helpers
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s&-]", "", (s or "").lower())).strip()


def _fmt(x: float) -> str:
    return str(int(x)) if x == int(x) else f"{x:.2f}"


def _waived(rule: dict, approvals: list[str]) -> bool:
    """True if any documented approval is listed in the rule's `waived_by` (policy.json)."""
    return any(a in (rule.get("waived_by") or []) for a in approvals)


def _high_value_threshold(policy: dict) -> float | None:
    """Amount above which the top approval tier applies (2000 AZN in v2.4), read from policy."""
    mins = [t["min"] for t in policy["approval_thresholds"] if t.get("required_approval")]
    return max(mins) if mins else None


def _covers(policy: dict, required: str, approvals: list[str]) -> bool:
    ok = set(policy["approval_covers"].get(required, [required]))
    return any(a in ok for a in approvals)


def _level_name(policy: dict, key: str | None) -> str:
    return policy["approval_levels"].get(key, key) if key else "None"


def normalize_category(policy: dict, raw: str | None) -> str | None:
    """Map free-text category onto a policy category, or None if uncovered."""
    n = _norm(raw or "")
    if not n:
        return None
    covered = {r["category"] for r in policy["rules"] if r.get("category")}
    for c in covered:
        if _norm(c) == n:
            return c
    for c, aliases in policy.get("category_aliases", {}).items():
        if any(re.search(rf"\b{re.escape(a)}\b", n) for a in aliases):
            return c
    return None


def _severity(over_ratio: float | None = None, high: bool = False) -> str:
    if high:
        return "high"
    if over_ratio is None:
        return "medium"
    if over_ratio >= 0.5:
        return "high"
    if over_ratio >= 0.15:
        return "medium"
    return "low"


def _tier_for(policy: dict, amount: float) -> dict | None:
    for t in policy["approval_thresholds"]:
        lo_ok = amount > t["min"] or (t["min_inclusive"] and amount == t["min"])
        hi_ok = t["max"] is None or amount < t["max"] or (t["max_inclusive"] and amount == t["max"])
        if lo_ok and hi_ok:
            return t
    return None


# ---------------------------------------------------------------- engine
def evaluate(policy: dict, ext: dict[str, Any]) -> dict[str, Any]:
    violations: list[dict] = []
    trace: list[dict] = []
    review: list[str] = []
    assumptions: list[str] = []
    extra_notes: list[str] = []

    vendor = (ext.get("vendor") or "").strip()
    currency = (ext.get("currency") or "").strip().upper()
    approvals = [a for a in (ext.get("approvals") or []) if a in policy["approval_levels"]]
    amount = ext.get("amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None

    # Approval claims that failed deterministic verification (approval_guard.py).
    verification = ext.get("approval_verification")
    if verification == "rejected":
        review.append(
            f"An approval was claimed but discarded: {ext.get('approval_rejection_reason') or 'not verifiable'}. "
            f"A person must confirm the approval before payment."
        )
    elif verification == "unverified" and approvals:
        assumptions.append(
            "Approval read from an image/scan could not be checked against document text; confirm it."
        )
    for flag in ext.get("security_flags") or []:
        review.append(flag + " This text was ignored; a person should check why it is there.")

    # Required-field completeness (missing data is never silently "fine").
    for f in policy.get("required_fields", []):
        v = ext.get(f)
        if v is None or (isinstance(v, str) and (not v.strip() or v.strip().lower() in
                                                  {"[not provided]", "n/a", "unknown", "none", "null"})):
            review.append(f"Required field '{f}' is missing from the record.")
            if f == "amount":
                amount = None

    category = normalize_category(policy, ext.get("category"))
    pol_cur = policy.get("currency", "AZN")
    amount_usable = amount is not None
    if amount_usable and amount <= 0:
        review.append(
            f"Amount is {_fmt(amount)}: zero or negative amounts (refunds, credit notes, unreadable totals) "
            f"are not expense claims this policy covers; amount-based rules were not evaluated."
        )
        amount_usable = False
    if amount_usable and currency and currency != pol_cur and not policy.get("fx_rates"):
        review.append(
            f"Invoice is in {currency} but policy limits are in {pol_cur} and no exchange rate "
            f"is defined; amount-based rules were not evaluated."
        )
        amount_usable = False
    if amount_usable and not currency:
        assumptions.append(f"No currency stated; assumed {pol_cur}.")

    nights = ext.get("nights")
    attendees = ext.get("attendees")
    tier = _tier_for(policy, amount) if amount_usable else None
    tier_rule_applied_and_met = False
    hv = _high_value_threshold(policy)
    required_levels: list[str] = []

    for rule in policy["rules"]:
        rid, chk = rule["id"], rule["check"]
        desc = rule["description"]

        # ---- per-person meal limit
        if chk == "per_person_limit":
            if category != rule["category"]:
                trace.append({"rule_id": rid, "result": "n/a", "calc": f"Category is not {rule['category']}."})
                continue
            if not amount_usable:
                trace.append({"rule_id": rid, "result": "skipped", "calc": "Amount unavailable or foreign currency."})
                continue
            n = attendees if isinstance(attendees, int) and attendees > 0 else None
            if n is None:
                n = 1
                assumptions.append(
                    f"{rid}: attendee count not stated; assumed 1 person (strictest reading)."
                )
            per = amount / n
            lim = rule["limit_amount"]
            calc = f"{_fmt(amount)} {pol_cur} / {n} person(s) = {_fmt(per)} per person vs limit {_fmt(lim)}"
            if per > lim:
                violations.append({
                    "rule_id": rid, "rule_description": desc, "severity": _severity((per - lim) / lim),
                    "explanation": f"Meal cost is {_fmt(per)} {pol_cur} per person ({_fmt(amount)} for {n}); "
                                   f"policy maximum is {_fmt(lim)} {pol_cur} per person per day.",
                })
                trace.append({"rule_id": rid, "result": "violation", "calc": calc})
            else:
                trace.append({"rule_id": rid, "result": "pass", "calc": calc})

        # ---- per-night hotel limit
        elif chk == "per_night_limit":
            if category != rule["category"]:
                trace.append({"rule_id": rid, "result": "n/a", "calc": f"Category is not {rule['category']}."})
                continue
            if not amount_usable:
                trace.append({"rule_id": rid, "result": "skipped", "calc": "Amount unavailable or foreign currency."})
                continue
            n = nights if isinstance(nights, int) and nights > 0 else None
            if n is None:
                n = 1
                assumptions.append(f"{rid}: number of nights not stated; assumed 1 night.")
            per = amount / n
            lim = rule["limit_amount"]
            calc = f"{_fmt(amount)} {pol_cur} / {n} night(s) = {_fmt(per)} per night vs limit {_fmt(lim)}"
            waived = _waived(rule, approvals)
            if per > lim and not waived:
                violations.append({
                    "rule_id": rid, "rule_description": desc, "severity": _severity((per - lim) / lim),
                    "explanation": f"Accommodation is {_fmt(per)} {pol_cur} per night ({_fmt(amount)} over {n} "
                                   f"night(s)); limit is {_fmt(lim)} {pol_cur} per night and no "
                                   f"{' / '.join(_level_name(policy, w) for w in rule.get('waived_by') or [])} "
                                   f"pre-approval is documented.",
                })
                trace.append({"rule_id": rid, "result": "violation", "calc": calc})
            else:
                trace.append({"rule_id": rid, "result": "pass",
                              "calc": calc + (" (waived by documented pre-approval)" if per > lim else "")})

        # ---- software over threshold needs IT approval
        elif chk == "approval_over_amount":
            if category != rule["category"]:
                trace.append({"rule_id": rid, "result": "n/a", "calc": f"Category is not {rule['category']}."})
                continue
            if not amount_usable:
                trace.append({"rule_id": rid, "result": "skipped", "calc": "Amount unavailable or foreign currency."})
                continue
            lim, need = rule["limit_amount"], rule["required_approval"]
            if amount > lim:
                required_levels.append(need)
                has = _covers(policy, need, approvals)
                calc = f"{_fmt(amount)} > {_fmt(lim)} {pol_cur}: {_level_name(policy, need)} approval required; documented: {'yes' if has else 'no'}"
                if not has:
                    violations.append({
                        "rule_id": rid, "rule_description": desc, "severity": _severity(None),
                        "explanation": f"Software purchase of {_fmt(amount)} {pol_cur} exceeds {_fmt(lim)} "
                                       f"{pol_cur}, so prior written {_level_name(policy, need)} approval is "
                                       f"required, but none is documented on the record.",
                    })
                    trace.append({"rule_id": rid, "result": "violation", "calc": calc})
                else:
                    trace.append({"rule_id": rid, "result": "pass", "calc": calc})
            else:
                trace.append({"rule_id": rid, "result": "pass",
                              "calc": f"{_fmt(amount)} <= {_fmt(lim)} {pol_cur}: no {_level_name(policy, need)} approval needed."})

        # ---- approved vendor list
        elif chk == "approved_vendor":
            listed = {_norm(v): v for v in policy["approved_vendors"]}
            if not vendor:
                trace.append({"rule_id": rid, "result": "skipped", "calc": "Vendor missing."})
                continue
            if _norm(vendor) in listed:
                trace.append({"rule_id": rid, "result": "pass", "calc": f"'{vendor}' is on the Approved Vendor List."})
            else:
                waived = _waived(rule, approvals)
                near = difflib.get_close_matches(_norm(vendor), list(listed), n=1, cutoff=0.8)
                if near:
                    extra_notes.append(
                        f"Vendor '{vendor}' is not an exact match for approved vendor '{listed[near[0]]}'. "
                        f"Possible typo or alias: confirm before rejecting."
                    )
                if waived:
                    trace.append({"rule_id": rid, "result": "pass",
                                  "calc": f"'{vendor}' not listed, but a waiving sign-off is documented."})
                else:
                    violations.append({
                        "rule_id": rid, "rule_description": desc,
                        "severity": _severity(None, high=bool(amount_usable and hv is not None and amount > hv)),
                        "explanation": f"Vendor '{vendor}' is not on the Approved Vendor List and no Finance "
                                       f"Director sign-off is documented on the record.",
                    })
                    trace.append({"rule_id": rid, "result": "violation", "calc": f"'{vendor}' not on list; no FD sign-off."})

        # ---- approval tiers
        elif chk == "approval_tiers":
            if not amount_usable or tier is None:
                trace.append({"rule_id": rid, "result": "skipped", "calc": "Amount unavailable or foreign currency."})
                continue
            need = tier["required_approval"]
            if need is None:
                trace.append({"rule_id": rid, "result": "pass",
                              "calc": f"{_fmt(amount)} {pol_cur} is in the tier '{tier['label']}' "
                                      f"(below {_fmt(tier['max'])} {pol_cur})." if tier.get("max") is not None
                                      else f"{_fmt(amount)} {pol_cur}: no approval required."})
                continue
            required_levels.append(need)
            has = _covers(policy, need, approvals)
            calc = f"{_fmt(amount)} {pol_cur} falls in tier '{tier['label']}': approval required; documented: {'yes' if has else 'no'}"
            if has:
                tier_rule_applied_and_met = True
                trace.append({"rule_id": rid, "result": "pass", "calc": calc})
            else:
                violations.append({
                    "rule_id": rid, "rule_description": desc,
                    "severity": _severity(None, high=(need == "finance_director")),
                    "explanation": f"Expense of {_fmt(amount)} {pol_cur} requires {tier['label']} approval "
                                   f"under the policy tiers, but no such approval is stated on the record.",
                })
                trace.append({"rule_id": rid, "result": "violation", "calc": calc})

    # Categories with no dedicated rule: never guess.
    if category is None and amount_usable:
        if not (policy["uncovered_category"]["action"] == "needs_review" and tier_rule_applied_and_met):
            review.append(
                f"Category '{ext.get('category') or 'unknown'}' has no dedicated policy rule, so "
                f"compliance cannot be confirmed automatically."
            )
        else:
            extra_notes.append(
                f"Category '{ext.get('category')}' has no dedicated rule; accepted because the amount's "
                f"approval tier is satisfied by documented approval."
            )

    # Status
    if violations:
        status = "flagged"
    elif review:
        status = "needs_review"
    else:
        status = "approved"

    if status == "needs_review":
        confidence = "low"
    elif assumptions or extra_notes:
        confidence = "medium"
    else:
        confidence = "high"

    # Required approvals summary
    if amount_usable and tier is not None:
        parts = []
        for lvl in dict.fromkeys(required_levels):
            parts.append(_level_name(policy, lvl))
        req = " + ".join(parts) if parts else "None (auto-approved)"
    else:
        req = "Cannot be determined"

    notes = " ".join(review + [f"Assumption: {a}" for a in assumptions] + extra_notes)
    if ext.get("approval_evidence"):
        notes = (notes + " " if notes else "") + f"Approval evidence read from record: \"{ext['approval_evidence']}\"."

    return {
        "vendor": vendor,
        "amount": amount,  # None when missing/unreadable (UI shows a dash, never a fake 0)
        "currency": currency or (pol_cur if amount is not None else ""),
        "category": ext.get("category") or "",
        "date": ext.get("date") or "",
        "employee": ext.get("employee") or "",
        "violations": violations,
        "status": status,
        "required_approval_level": req,
        "confidence": confidence,
        "notes": notes.strip(),
        "trace": trace,
        "assumptions": assumptions,
        "needs_review_reasons": review,
        "approvals_found": approvals,
        "approval_verification": verification or ("verified" if approvals else "none"),
        "security_flags": list(ext.get("security_flags") or []),
    }
