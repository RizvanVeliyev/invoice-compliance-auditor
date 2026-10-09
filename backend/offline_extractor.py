"""
Offline (no-LLM) extractor for the 'EXPENSE RECORD' template format.

Purpose: lets the whole pipeline (rules engine, API, quality tests) run with
no API key, and gives the quality tests a reproducible extraction step so the
rules engine can be verified in isolation. It is NOT a substitute for the LLM:
it cannot read free text, other languages, multi-line tables or scans. Cases
that need real language understanding are tagged "llm_only" in test_cases.json.
"""

import re

CUR = {"AZN": "AZN", "₼": "AZN", "USD": "USD", "$": "USD", "EUR": "EUR", "€": "EUR",
       "GBP": "GBP", "£": "GBP", "TRY": "TRY", "RUB": "RUB"}


def _field(text: str, name: str) -> str:
    m = re.search(rf"^\s*{name}\s*:\s*(.*)$", text, re.I | re.M)
    return m.group(1).strip() if m else ""


_CUR_RE = r"(AZN|USD|EUR|GBP|TRY|RUB|manat|[$€£₼])"


def _parse_number(tok: str) -> float | None:
    """Parse '1 234,50', '1.234,50', '1,234.50', '1234.5', '900' correctly."""
    tok = re.sub(r"\s+", "", tok)
    if "," in tok and "." in tok:
        dec = "," if tok.rfind(",") > tok.rfind(".") else "."
        tok = tok.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in tok:
        # 1,234 / 12,345,678 -> thousands; 12,5 / 1234,50 -> decimal comma
        tok = tok.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", tok) else tok.replace(",", ".")
    elif tok.count(".") > 1:
        tok = tok.replace(".", "")          # 1.234.567 -> thousands dots
    try:
        return float(tok)
    except ValueError:
        return None


def _amount(raw: str):
    """Amount and currency from a line like '900 AZN', 'AZN 900', '₼1 234,50', '$180'."""
    m = re.search(r"\d[\d\s.,]*\d|\d", raw)
    if not m:
        return None, ""
    num = _parse_number(m.group(0).strip())
    # Credit notes: "-240", "− 240", "₼-240" or accounting style "(240)" are negative.
    before = raw[:m.start()]
    if num is not None and (re.search(r"[-−–]\s*[$€£₼]?\s*$", before) or
                            (before.rstrip().endswith("(") and raw[m.end():].lstrip().startswith(")"))):
        num = -num
    cm = re.search(_CUR_RE, raw, re.I)
    cur = cm.group(1) if cm else ""
    cur = "AZN" if cur.lower() == "manat" else cur.upper() if cur.isalpha() else cur
    return num, CUR.get(cur, cur)


_NEG = re.compile(
    r"\b(not (yet|been|approved|given|received|signed)|pending|requested|awaiting|to be approved|will be"
    r"|rejected|declined|denied|refused|unapproved|no approval)\b",
    re.I)


def _approvals(raw: str):
    return _approvals_with_evidence(raw)[0]


def _approvals_with_evidence(raw: str):
    """Approvals stated as GIVEN on the 'Approval:' line.

    Each clause is checked on its own, so 'Approved by IT; manager approval pending'
    keeps IT and drops Manager. 'IT' must be the upper-case word or 'IT department',
    so 'Manager approved it' is not read as IT approval.
    """
    if not raw or not raw.strip():
        return [], ""
    if re.match(r"^\s*(none|n/a|na|no|-)\b", raw, re.I) or "none stated" in raw.lower():
        return [], ""
    out, used = [], []
    for clause in re.split(r"[;,]|\.(?=\s|$)|\bbut\b|\bhowever\b", raw, flags=re.I):
        c = clause.lower()
        n_before = len(out)
        if not c.strip() or _NEG.search(clause):
            continue
        if "finance director" in c:
            out.append("finance_director")
        elif re.search(r"\bdirector\b", c):
            out.append("director")
        if re.search(r"\bmanager\b", c):
            out.append("manager")
        if re.search(r"\bIT\b", clause) or re.search(r"\bit (department|dept|team)\b", c):
            out.append("it")
        if len(out) > n_before:
            used.append(clause.strip())
    return list(dict.fromkeys(out)), "; ".join(used)


_INVOICE_NO = (
    r"^\s*(?:invoice|receipt|bill|document)\s*(?:no|number|num)?\s*[.:#№]*\s*([A-Za-z0-9][\w/-]*)\s*$",
    r"^\s*(?:no|№)\s*[.:]\s*([A-Za-z0-9][\w/-]*)\s*$",
)


def _invoice_number(text: str) -> str:
    """'Invoice No: X', 'Invoice #X', 'Receipt No. X' or a bare 'No. X' line. Must contain a digit."""
    for pat in _INVOICE_NO:
        for m in re.finditer(pat, text, re.I | re.M):
            if re.search(r"\d", m.group(1)):
                return m.group(1)
    return ""


def extract(text: str) -> dict:
    amount_raw = _field(text, "Amount")
    amount, currency = _amount(amount_raw) if amount_raw else (None, "")
    desc = _field(text, "Description")
    blob = " ".join([desc, amount_raw, _field(text, "Date")])

    nights = None
    m = re.search(r"(\d+)\s*[- ]?nights?", blob, re.I)
    if m:
        nights = int(m.group(1))

    attendees = None
    if re.search(r"single attendee|one person|1 person|alone", text, re.I):
        attendees = 1
    else:
        m = re.search(r"with\s+(\d+)\s+(?:clients?|guests?|partners?|colleagues?)", desc, re.I)
        if m:
            attendees = int(m.group(1)) + 1
        m = re.search(r"(\d+)\s+(?:people|attendees|persons|guests)", text, re.I)
        if m:
            attendees = int(m.group(1))

    appr_raw = _field(text, "Approval")
    approvals, evidence = _approvals_with_evidence(appr_raw)
    date = _field(text, "Date")
    if date.startswith("[") or date.lower() in {"", "n/a"}:
        date = ""
    return {
        "vendor": _field(text, "Vendor"),
        "invoice_number": _invoice_number(text),
        "amount": amount,
        "currency": currency,
        "category": _field(text, "Category"),
        "date": date,
        "employee": _field(text, "Employee"),
        "description": desc,
        "nights": nights,
        "attendees": attendees,
        "approvals": approvals,
        "approval_evidence": evidence,
    }
