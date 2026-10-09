"""
Baseline: what a plain amount-threshold filter (the kind of rule people build
in a spreadsheet) would do. It checks only category limits on the raw invoice
total and a flat 2000 cap. It does NOT divide by people/nights, check the
vendor list, read approvals, or look at currency/dates. It is a proxy for
"the current approach", not a measurement of human reviewers.
"""
import offline_extractor

LIMITS = {"meals": 150, "hotel": 300, "software": 1000}


def naive_status(text: str) -> tuple[str, list[str]]:
    r = offline_extractor.extract(text)
    amt = r["amount"] or 0
    cat = (r["category"] or "").lower()
    rules = []
    if "meal" in cat and amt > LIMITS["meals"]:
        rules.append("EXP-1.1")
    if "accommodation" in cat and amt > LIMITS["hotel"]:
        rules.append("EXP-1.2")
    if "software" in cat and amt > LIMITS["software"]:
        rules.append("EXP-2.1")
    if amt > 2000:
        rules.append("EXP-4.1")
    return ("flagged" if rules else "approved"), rules
