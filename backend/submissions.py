"""
Employee submissions and auditor alerts.

Flow:
  signed-in employee uploads an invoice PDF (or photo)  ->  file is validated
  -> duplicate check on the file itself (before any AI call)
  -> service.analyze() (AI extraction + deterministic rules)
  -> duplicate check on the invoice's content (vendor + invoice number, or
     vendor + amount + currency + date)
  -> file stored, submission row written
  -> if the result needs attention, an alert appears on the auditor desk
     (and is optionally pushed to a webhook such as Slack / Teams / Discord).

A duplicate is refused, not stored: the employee is told which earlier
submission it matches, and the attempt is recorded for the audit team.
A readable-or-not original is never lost: if the document cannot be read
automatically it is stored as needs_review and the auditor is alerted.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import threading
import urllib.request
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mailer
import rules_engine
import service

log = logging.getLogger("ledger.submissions")

ALLOWED = {
    "application/pdf": (b"%PDF-", ".pdf"),
    "image/png": (b"\x89PNG", ".png"),
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
    "image/webp": (b"RIFF", ".webp"),
}
DECISIONS = {"approved", "rejected"}

# Columns added after the first release; created on older databases by _db().
_EXTRA_COLUMNS = {
    "user_id": "INTEGER", "reviewer_id": "INTEGER", "vendor_key": "TEXT", "invoice_no_key": "TEXT",
    "amount": "REAL", "currency": "TEXT", "amount_policy": "REAL", "invoice_date": "TEXT",
}

_in_flight: set[str] = set()          # SHA-256 of files being analysed right now
_in_flight_lock = threading.Lock()


class DuplicateInvoice(ValueError):
    """The upload matches an earlier submission and was refused."""

    def __init__(self, message: str, original_id: int | None):
        super().__init__(message)
        self.original_id = original_id


# ------------------------------------------------------------------ storage
def _uploads_dir() -> Path:
    d = service.DB_PATH.parent / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _db():
    con = service._db()
    con.execute(
        "CREATE TABLE IF NOT EXISTS submissions ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, employee_name TEXT, employee_email TEXT, note TEXT,"
        " filename TEXT, stored_name TEXT, mime TEXT, size INTEGER, sha256 TEXT,"
        " status TEXT, alert INTEGER, warnings_json TEXT, result_json TEXT,"
        " review_state TEXT DEFAULT 'new', decision TEXT, decision_comment TEXT, reviewer TEXT, decided_at TEXT)"
    )
    have = {r[1] for r in con.execute("PRAGMA table_info(submissions)").fetchall()}
    for col, kind in _EXTRA_COLUMNS.items():
        if col not in have:
            con.execute(f"ALTER TABLE submissions ADD COLUMN {col} {kind}")
    # Everything that happens to a submission, in order: who sent it, each decision, a reopening,
    # and the auditors' internal notes. Rows are only ever added.
    con.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id INTEGER, ts TEXT, user_id INTEGER, user_name TEXT,"
        " kind TEXT, text TEXT)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS duplicate_blocks ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user_id INTEGER, user_name TEXT, filename TEXT,"
        " sha256 TEXT, original_id INTEGER, reason TEXT)"
    )
    con.row_factory = sqlite3.Row
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sniff_mime(data: bytes, declared: str, filename: str) -> str:
    """Trust the file's bytes, not the browser's label."""
    for mime, (magic, _) in ALLOWED.items():
        if data.startswith(magic):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    raise ValueError("Only PDF, PNG, JPEG or WEBP files can be submitted. "
                     f"'{filename or 'file'}' is not one of these.")


EVENT_KINDS = {"submitted", "approved", "rejected", "reopened", "note", "email", "email_failed"}
INTERNAL_EVENTS = {"note", "email_failed"}        # shown to the audit team only
SYSTEM = {"id": None, "name": "FiscalAI"}          # the author of events nobody clicked for


def _event(con, sid: int, user: dict, kind: str, text: str = "") -> None:
    con.execute("INSERT INTO events (submission_id, ts, user_id, user_name, kind, text) VALUES (?,?,?,?,?,?)",
                (sid, _now(), user["id"], user["name"][:120], kind, (text or "").strip()[:1000]))


def _events(con, sid: int, internal: bool = True) -> list[dict]:
    rows = con.execute("SELECT * FROM events WHERE submission_id=? ORDER BY id", (sid,)).fetchall()
    return [{"id": e["id"], "ts": e["ts"], "user_name": e["user_name"], "kind": e["kind"], "text": e["text"]}
            for e in rows if internal or e["kind"] not in INTERNAL_EVENTS]


def _mail_recorder(sid: int, to: str):
    """Callback for the mailer: write into the invoice's history whether the employee was told."""
    def record(error: str | None) -> None:
        con = _db()
        try:
            with con:
                _event(con, sid, SYSTEM, "email_failed" if error else "email", f"{to}: {error}" if error else to)
        finally:
            con.close()
    return record


# ------------------------------------------------------------------ duplicates
# A submission that an auditor rejected does not block a new upload: the employee
# is expected to fix the problem and send the invoice again.
_LIVE = "(decision IS NULL OR decision <> 'rejected')"


def _invoice_no_key(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _whose(row: sqlite3.Row, user_id: int) -> str:
    return "by you" if row["user_id"] == user_id else "by a colleague"


def _refuse(con, user: dict, filename: str, sha: str, original: sqlite3.Row, what: str) -> None:
    reason = f"{what} as submission #{original['id']}"
    with con:
        con.execute(
            "INSERT INTO duplicate_blocks (ts, user_id, user_name, filename, sha256, original_id, reason)"
            " VALUES (?,?,?,?,?,?,?)",
            (_now(), user["id"], user["name"], (filename or "invoice")[:200], sha, original["id"], reason))
    raise DuplicateInvoice(
        f"This invoice was already submitted {_whose(original, user['id'])} on {original['ts'][:10]} "
        f"(submission #{original['id']}): {what}. Duplicate invoices are not accepted. If this is a "
        f"different purchase, ask the audit team to check submission #{original['id']}.",
        original["id"])


def _same_file(con, sha: str) -> sqlite3.Row | None:
    return con.execute(f"SELECT * FROM submissions WHERE sha256=? AND {_LIVE} ORDER BY id LIMIT 1",
                       (sha,)).fetchone()


def _same_invoice(con, result: dict) -> tuple[sqlite3.Row, str] | None:
    """An earlier live submission of the same invoice in a different file (re-scan, re-export, photo)."""
    vendor = service._key(result.get("vendor"))
    if not vendor:
        return None
    number = _invoice_no_key(result.get("invoice_number"))
    if number:
        r = con.execute(
            f"SELECT * FROM submissions WHERE vendor_key=? AND invoice_no_key=? AND {_LIVE} ORDER BY id LIMIT 1",
            (vendor, number)).fetchone()
        if r:
            return r, f"same vendor and invoice number ({result['invoice_number']})"
    amount, date = result.get("amount"), (result.get("date") or "").strip()
    if isinstance(amount, (int, float)) and amount > 0 and date:
        cur = result.get("currency") or ""
        for r in con.execute(
                f"SELECT * FROM submissions WHERE vendor_key=? AND invoice_date=? AND currency=? AND {_LIVE}"
                f" ORDER BY id", (vendor, date, cur)).fetchall():
            # Two different invoice numbers are two invoices, even with equal totals on one day.
            if number and r["invoice_no_key"] and r["invoice_no_key"] != number:
                continue
            if r["amount"] is not None and abs(r["amount"] - amount) < 0.005:
                return r, f"same vendor, amount ({amount:g} {cur}) and date ({date})"
    return None


# ------------------------------------------------------------------ checks around the AI verdict
def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"\w+", (s or "").lower()) if len(t) >= 3}


def submission_warnings(con, name: str, sha: str, result: dict) -> list[str]:
    warnings = []
    extracted = result.get("employee") or ""
    if extracted and name and not (_tokens(extracted) & _tokens(name)):
        warnings.append(f"Submitted by '{name}', but the invoice names '{extracted}' as the employee.")
    prev = con.execute("SELECT id, ts FROM submissions WHERE sha256=? AND decision='rejected' ORDER BY id",
                       (sha,)).fetchall()
    for p in prev[:3]:
        warnings.append(f"This exact file was submitted before as #{p['id']} on {p['ts'][:10]} and rejected.")
    return warnings


def employee_message(status: str, alert: bool) -> str:
    if status == "approved" and not alert:
        return "Your invoice follows the expense policy. It has been passed to Finance for payment."
    if status == "flagged":
        return ("Your invoice breaks one or more expense-policy rules. It has been sent to the audit team, "
                "who may contact you. The reasons are listed below.")
    return ("Your invoice needs a person to check it before it can be paid. It has been sent to the audit team.")


def _unreadable_result(reason: str) -> dict:
    return {
        "vendor": "", "invoice_number": "", "amount": None, "currency": "", "amount_policy": None,
        "category": "", "date": "", "employee": "",
        "violations": [], "status": "needs_review", "required_approval_level": "Cannot be determined",
        "confidence": "low", "notes": reason, "trace": [], "assumptions": [],
        "needs_review_reasons": [reason], "approvals_found": [], "history_warnings": [],
        "meta": {"provider": os.environ.get("LLM_PROVIDER", "offline"), "source": "unreadable"},
    }


# ------------------------------------------------------------------ alerts
def _notify(row: dict) -> None:
    """POST a short alert to ALERT_WEBHOOK_URL (Slack/Teams/Discord-compatible). Fire and forget."""
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return
    base = os.environ.get("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/")
    text = (f"Ledger alert: invoice #{row['id']} from {row['employee_name']} is {row['status'].replace('_', ' ')}"
            f" ({row.get('vendor') or 'unknown vendor'}, {row.get('amount_label')}). "
            f"Review: {base}/audit?id={row['id']}")
    body = json.dumps({"text": text, "content": text, "submission": row}).encode()

    def send():
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=8).read()
        except Exception:  # noqa: BLE001
            log.exception("Alert webhook failed")

    threading.Thread(target=send, daemon=True).start()


# ------------------------------------------------------------------ public API
def create(policy: dict, data: bytes, declared_mime: str, filename: str, user: dict,
           note: str = "", currency: str = "") -> dict:
    """Check and store one invoice for the signed-in `user`. Raises DuplicateInvoice for a repeat."""
    currency = (currency or "").strip().upper()
    accepted = policy.get("accepted_currencies") or [policy.get("currency", "AZN")]
    if currency and currency not in accepted:
        raise ValueError(f"Ledger accepts invoices in {', '.join(accepted)}. '{currency}' is not one of these.")
    mime = sniff_mime(data, declared_mime, filename)
    sha = hashlib.sha256(data).hexdigest()

    con = _db()
    try:
        same = _same_file(con, sha)
        if same:
            _refuse(con, user, filename, sha, same, "it is the same file")
        with _in_flight_lock:
            if sha in _in_flight:
                raise DuplicateInvoice("This file is being checked right now. Wait for that result instead of "
                                       "sending it again.", None)
            _in_flight.add(sha)
        try:
            return _create(con, policy, data, mime, sha, filename, user, note, currency)
        finally:
            with _in_flight_lock:
                _in_flight.discard(sha)
    finally:
        con.close()


def _create(con, policy: dict, data: bytes, mime: str, sha: str, filename: str, user: dict,
            note: str, currency: str) -> dict:
    name = user["name"]
    try:
        result = service.analyze(policy, file_bytes=data, mime=mime, default_currency=currency or None)
    except KeyError as e:
        result = _unreadable_result(f"Automatic reading is not configured on the server (missing {e}). "
                                    f"A person must read this invoice.")
    except Exception as e:  # noqa: BLE001 - never lose an employee's submission
        if isinstance(e, ValueError):
            log.info("Submission could not be read automatically: %s", e)
        else:
            log.exception("Analysis failed for submission")
        msg = str(e)
        if "Offline provider" in msg or "text layer" in msg or "scanned" in msg:
            msg = ("This file has no readable text (it looks scanned or photographed) and no AI model is "
                   "configured to read images. A person must read this invoice.")
        result = _unreadable_result(f"The invoice could not be read automatically: {msg}")

    match = _same_invoice(con, result)
    if match:
        _refuse(con, user, filename, sha, *match)

    stored = f"{uuid.uuid4().hex}{ALLOWED[mime][1]}"
    (_uploads_dir() / stored).write_bytes(data)

    # Real duplicates were refused above; what is left of the audit-log comparison is noise here
    # (for example the same invoice tried in Quick check first).
    history = [w for w in result.get("history_warnings") or [] if not w.startswith("Possible duplicate")]
    warnings = history + submission_warnings(con, name, sha, result)
    result["history_warnings"] = warnings
    status = result["status"]
    alert = status != "approved" or bool(warnings)
    amount = result.get("amount") if isinstance(result.get("amount"), (int, float)) else None
    with con:
        cur = con.execute(
            "INSERT INTO submissions (ts, employee_name, employee_email, note, filename, stored_name, mime, size,"
            " sha256, status, alert, warnings_json, result_json, review_state, user_id, vendor_key, invoice_no_key,"
            " amount, currency, amount_policy, invoice_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_now(), name[:120], user["email"][:200], (note or "").strip()[:1000],
             (filename or "invoice")[:200], stored, mime, len(data), sha, status, int(alert),
             json.dumps(warnings), json.dumps(result), "new" if alert else "auto_cleared", user["id"],
             service._key(result.get("vendor")), _invoice_no_key(result.get("invoice_number")),
             amount, result.get("currency") or "", result.get("amount_policy"), (result.get("date") or "").strip()),
        )
        sid = cur.lastrowid
        _event(con, sid, user, "submitted", note)
    row = summary(con.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone())
    if alert:
        _notify(row)
    else:                                   # approved by the policy check itself: tell the employee now
        mailer.notify_auto_cleared(row, _mail_recorder(sid, row["employee_email"]))

    return {
        "id": sid,
        "status": status,
        "sent_to_audit": alert,
        "message": employee_message(status, alert),
        "vendor": result.get("vendor"), "invoice_number": result.get("invoice_number") or "",
        "amount": result.get("amount"), "currency": result.get("currency"),
        "amount_policy": result.get("amount_policy"), "policy_currency": policy.get("currency", "AZN"),
        "conversion": result.get("conversion"),
        "category": result.get("category"), "date": result.get("date"), "employee": result.get("employee"),
        "violations": [{"rule_id": v["rule_id"], "explanation": v["explanation"], "severity": v["severity"]}
                       for v in result.get("violations", [])],
        "review_reasons": result.get("needs_review_reasons", []),
        "warnings": warnings,
        "meta": result.get("meta", {}),
    }


def _label(amt, cur: str) -> str:
    if not isinstance(amt, (int, float)):
        return "amount unreadable"
    return (f"{amt:,.0f} {cur}" if amt == int(amt) else f"{amt:,.2f} {cur}").strip()


def summary(r: sqlite3.Row) -> dict:
    res = json.loads(r["result_json"] or "{}")
    amt, cur = res.get("amount"), res.get("currency") or ""
    return {
        "id": r["id"], "ts": r["ts"], "employee_name": r["employee_name"], "employee_email": r["employee_email"],
        "user_id": r["user_id"],
        "filename": r["filename"], "status": r["status"], "alert": bool(r["alert"]),
        "review_state": r["review_state"], "decision": r["decision"],
        "vendor": res.get("vendor") or "", "invoice_number": res.get("invoice_number") or "",
        "amount": amt, "currency": cur, "amount_label": _label(amt, cur),
        "amount_policy": res.get("amount_policy"), "conversion": res.get("conversion"),
        "category": res.get("category") or "",
        "violation_ids": [v["rule_id"] for v in res.get("violations", [])],
        "warning_count": len(json.loads(r["warnings_json"] or "[]")),
    }


def _filtered(status: str | None, state: str | None, search: str | None, user_id: int | None,
              currency: str | None, date_from: str | None, date_to: str | None) -> tuple[str, list]:
    """WHERE clause shared by the list and its total, so a page and its count can never disagree."""
    q, args = " WHERE 1=1", []
    if user_id is not None:
        q += " AND user_id=?"
        args.append(user_id)
    term = (search or "").strip().lower()[:80]
    if term.startswith("#") and term[1:].isdigit():          # "#12" means exactly that submission
        q += " AND id=?"
        args.append(int(term[1:]))
    elif term:
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses = ["LOWER(employee_name) LIKE ? ESCAPE '\\'", "vendor_key LIKE ? ESCAPE '\\'",
                   "LOWER(filename) LIKE ? ESCAPE '\\'", "LOWER(employee_email) LIKE ? ESCAPE '\\'"]
        args += [like, "%" + service._key(term) + "%" if service._key(term) else like, like, like]
        number = _invoice_no_key(term)
        if number:
            clauses.append("invoice_no_key LIKE ?")
            args.append(f"%{number}%")
        if term.isdigit():
            clauses.append("id=?")
            args.append(int(term))
        q += " AND (" + " OR ".join(clauses) + ")"
    if status:
        q += " AND status=?"
        args.append(status)
    if state == "open":
        q += " AND alert=1 AND decision IS NULL"
    elif state == "decided":
        q += " AND decision IS NOT NULL"
    if currency:
        q += " AND currency=?"
        args.append(currency.strip().upper()[:8])
    # Submission dates are stored as UTC timestamps; a filter day covers that whole UTC day.
    if date_from and _is_day(date_from):
        q += " AND substr(ts, 1, 10) >= ?"
        args.append(date_from)
    if date_to and _is_day(date_to):
        q += " AND substr(ts, 1, 10) <= ?"
        args.append(date_to)
    return q, args


def _is_day(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or ""))


def list_(status: str | None = None, state: str | None = None, limit: int = 100,
          search: str | None = None, user_id: int | None = None, currency: str | None = None,
          date_from: str | None = None, date_to: str | None = None, offset: int = 0) -> list[dict]:
    """Submissions, newest first. `search` matches the employee, vendor, invoice number, file name or #id."""
    return list_page(status, state, limit, search, user_id, currency, date_from, date_to, offset)[0]


def list_page(status: str | None = None, state: str | None = None, limit: int = 100,
              search: str | None = None, user_id: int | None = None, currency: str | None = None,
              date_from: str | None = None, date_to: str | None = None, offset: int = 0) -> tuple[list[dict], int]:
    """One page of submissions and how many match in total."""
    where, args = _filtered(status, state, search, user_id, currency, date_from, date_to)
    con = _db()
    total = con.execute("SELECT COUNT(*) FROM submissions" + where, args).fetchone()[0]
    rows = [summary(r) for r in con.execute(
        "SELECT * FROM submissions" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
        (*args, max(1, min(limit, 500)), max(0, offset))).fetchall()]
    con.close()
    return rows, total


def outcome(r: sqlite3.Row | dict) -> str:
    """Where an invoice stands, in the employee's terms."""
    if r["decision"] == "approved":
        return "cleared"
    if r["decision"] == "rejected":
        return "rejected"
    return "in_review" if r["alert"] else "cleared"


def list_mine(user_id: int, limit: int = 100) -> list[dict]:
    """The signed-in employee's own invoices with what happened to each. No auditor-only detail."""
    con = _db()
    rows = con.execute("SELECT * FROM submissions WHERE user_id=? ORDER BY id DESC LIMIT ?",
                       (user_id, max(1, min(limit, 500)))).fetchall()
    out = []
    for r in rows:
        res = json.loads(r["result_json"] or "{}")
        row = summary(r)
        row.update(
            events=_events(con, r["id"], internal=False),
            outcome=outcome(r), note=r["note"], decision_comment=r["decision_comment"], reviewer=r["reviewer"],
            decided_at=r["decided_at"], date=res.get("date") or "",
            violations=[{"rule_id": v["rule_id"], "explanation": v["explanation"], "severity": v["severity"]}
                        for v in res.get("violations", [])],
            review_reasons=res.get("needs_review_reasons", []))
        out.append(row)
    con.close()
    return out


def get(sid: int) -> dict | None:
    con = _db()
    r = con.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    events = _events(con, sid) if r else []
    con.close()
    if not r:
        return None
    out = summary(r)
    out.update(events=events, note=r["note"], mime=r["mime"], size=r["size"], sha256=r["sha256"],
               decision_comment=r["decision_comment"], reviewer=r["reviewer"], reviewer_id=r["reviewer_id"],
               decided_at=r["decided_at"],
               warnings=json.loads(r["warnings_json"] or "[]"), result=json.loads(r["result_json"] or "{}"))
    return out


def file_path(sid: int) -> tuple[Path, str, str, int | None] | None:
    con = _db()
    r = con.execute("SELECT stored_name, mime, filename, user_id FROM submissions WHERE id=?", (sid,)).fetchone()
    con.close()
    if not r:
        return None
    p = _uploads_dir() / r["stored_name"]
    return (p, r["mime"], r["filename"], r["user_id"]) if p.exists() else None


def mark_seen(sid: int) -> None:
    con = _db()
    with con:
        con.execute("UPDATE submissions SET review_state='seen' WHERE id=? AND review_state='new'", (sid,))
    con.close()


def decide(sid: int, decision: str, comment: str, reviewer: dict) -> dict | None:
    """Record the auditor's decision. Nobody decides on an invoice they submitted themselves."""
    if decision not in DECISIONS:
        raise ValueError("Decision must be 'approved' or 'rejected'.")
    if decision == "rejected" and not (comment or "").strip():
        raise ValueError("Add a short reason when rejecting, so the employee knows what to fix.")
    con = _db()
    try:
        r = con.execute("SELECT user_id, decision, reviewer FROM submissions WHERE id=?", (sid,)).fetchone()
        if not r:
            return None
        if r["user_id"] is not None and r["user_id"] == reviewer["id"]:
            raise PermissionError("You submitted this invoice yourself, so another auditor has to decide on it.")
        if r["decision"]:
            raise ValueError(f"{r['reviewer'] or 'An auditor'} already decided on this invoice. "
                             f"Reopen it first if the decision has to change.")
        with con:
            _event(con, sid, reviewer, decision, comment)
            con.execute(
                "UPDATE submissions SET decision=?, decision_comment=?, reviewer=?, reviewer_id=?, decided_at=?,"
                " review_state='decided' WHERE id=?",
                (decision, (comment or "").strip()[:1000], reviewer["name"][:120], reviewer["id"], _now(), sid))
    finally:
        con.close()
    decided = get(sid)
    # Email to the employee; never blocks or fails the decision, and the outcome lands in the history.
    mailer.notify_decision(decided, _mail_recorder(sid, decided["employee_email"]))
    return decided


def reopen(sid: int, reason: str, reviewer: dict) -> dict | None:
    """Take a decision back: the invoice returns to the open queue and the old decision stays in the timeline."""
    if not (reason or "").strip():
        raise ValueError("Say why the decision is being reopened; it is kept in the invoice's history.")
    con = _db()
    try:
        r = con.execute("SELECT user_id, decision FROM submissions WHERE id=?", (sid,)).fetchone()
        if not r:
            return None
        if not r["decision"]:
            raise ValueError("This invoice has no decision to reopen.")
        if r["user_id"] is not None and r["user_id"] == reviewer["id"]:
            raise PermissionError("You submitted this invoice yourself, so another auditor has to reopen it.")
        with con:
            _event(con, sid, reviewer, "reopened", reason)
            con.execute(
                "UPDATE submissions SET decision=NULL, decision_comment=NULL, reviewer=NULL, reviewer_id=NULL,"
                " decided_at=NULL, review_state='seen', alert=1 WHERE id=?", (sid,))
    finally:
        con.close()
    return get(sid)


def add_note(sid: int, text: str, author: dict) -> dict | None:
    """An internal note for the audit team. The employee never sees it."""
    if not (text or "").strip():
        raise ValueError("Write the note first.")
    con = _db()
    try:
        if not con.execute("SELECT 1 FROM submissions WHERE id=?", (sid,)).fetchone():
            return None
        with con:
            _event(con, sid, author, "note", text)
    finally:
        con.close()
    return get(sid)


def alert_summary() -> dict:
    con = _db()
    one = lambda q: con.execute(q).fetchone()[0]  # noqa: E731
    out = {
        "unread": one("SELECT COUNT(*) FROM submissions WHERE alert=1 AND review_state='new'"),
        "open": one("SELECT COUNT(*) FROM submissions WHERE alert=1 AND decision IS NULL"),
        "flagged": one("SELECT COUNT(*) FROM submissions WHERE status='flagged' AND decision IS NULL"),
        "needs_review": one("SELECT COUNT(*) FROM submissions WHERE status='needs_review' AND decision IS NULL"),
        "decided": one("SELECT COUNT(*) FROM submissions WHERE decision IS NOT NULL"),
        "total": one("SELECT COUNT(*) FROM submissions"),
        "latest_id": one("SELECT COALESCE(MAX(id), 0) FROM submissions"),
    }
    con.close()
    return out


# ------------------------------------------------------------------ overview
def overview(policy: dict, days: int = 14) -> dict:
    """Everything the audit lead needs to follow the flow of invoices: volumes, money, rules, people."""
    pol_cur = policy.get("currency", "AZN")
    con = _db()
    rows = con.execute("SELECT * FROM submissions ORDER BY id").fetchall()
    blocks = con.execute("SELECT * FROM duplicate_blocks ORDER BY id DESC").fetchall()
    con.close()

    counts = Counter()
    money = Counter()                      # policy-currency totals per outcome
    by_currency: dict[str, dict] = {}
    by_rule = Counter()
    people: dict[str, dict] = defaultdict(lambda: {"count": 0, "flagged": 0, "rejected": 0, "amount_policy": 0.0})
    unconverted = 0
    hours = []
    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=days - 1)
    daily = {(first_day + timedelta(days=i)).isoformat(): {"approved": 0, "flagged": 0, "needs_review": 0}
             for i in range(days)}

    for r in rows:
        res = json.loads(r["result_json"] or "{}")
        state = outcome(r)
        counts["total"] += 1
        counts[r["status"]] += 1
        counts[state] += 1
        if state == "cleared" and r["decision"] is None:
            counts["auto_cleared"] += 1
        value = r["amount_policy"]
        if value is None and r["amount"] is not None:
            # Rows written before amounts were stored per currency, or in a currency without a rate.
            rate = rules_engine.fx_rate(policy, r["currency"])
            value = round(r["amount"] * rate, 2) if rate else None
        if isinstance(value, (int, float)) and value > 0:
            money["submitted"] += value
            money[state] += value
        elif r["amount"] is not None:
            unconverted += 1
        if r["amount"] is not None:
            c = by_currency.setdefault(r["currency"] or pol_cur, {"count": 0, "amount": 0.0, "amount_policy": 0.0})
            c["count"] += 1
            c["amount"] += r["amount"]
            c["amount_policy"] += value or 0.0
        for v in res.get("violations", []):
            by_rule[v["rule_id"]] += 1
        p = people[r["employee_name"] or "Unknown"]
        p["count"] += 1
        p["flagged"] += r["status"] == "flagged"
        p["rejected"] += r["decision"] == "rejected"
        p["amount_policy"] += value or 0.0
        if r["ts"][:10] in daily:
            daily[r["ts"][:10]][r["status"]] += 1
        if r["decided_at"]:
            try:
                took = datetime.fromisoformat(r["decided_at"]) - datetime.fromisoformat(r["ts"])
                hours.append(took.total_seconds() / 3600)
            except ValueError:
                pass

    descriptions = {x["id"]: x["description"] for x in policy["rules"]}
    decided = sorted((r for r in rows if r["decided_at"]), key=lambda r: r["decided_at"], reverse=True)
    by_auditor = Counter(r["reviewer"] or "Unknown" for r in decided)
    return {
        "policy_currency": pol_cur,
        "fx_rates": policy.get("fx_rates") or {},
        "counts": {k: counts[k] for k in ("total", "approved", "flagged", "needs_review", "in_review", "cleared",
                                          "auto_cleared", "rejected")} | {"duplicates_blocked": len(blocks)},
        "money": {k: round(money[k], 2) for k in ("submitted", "cleared", "in_review", "rejected")},
        "unconverted": unconverted,
        "avg_decision_hours": round(sum(hours) / len(hours), 2) if hours else None,
        "decisions": len(hours),
        "by_currency": [{"currency": k, "count": v["count"], "amount": round(v["amount"], 2),
                         "amount_policy": round(v["amount_policy"], 2)}
                        for k, v in sorted(by_currency.items(), key=lambda kv: -kv[1]["amount_policy"])],
        "by_rule": [{"rule_id": k, "count": n, "description": descriptions.get(k, "")}
                    for k, n in sorted(by_rule.items(), key=lambda kv: (-kv[1], kv[0]))],
        "by_employee": [{"name": k, **{f: (round(x, 2) if f == "amount_policy" else x) for f, x in v.items()}}
                        for k, v in sorted(people.items(), key=lambda kv: (-kv[1]["count"], kv[0]))[:10]],
        "by_day": [{"date": d, **v} for d, v in daily.items()],
        "recent_decisions": [
            {"id": r["id"], "decided_at": r["decided_at"], "reviewer": r["reviewer"] or "", "decision": r["decision"],
             "comment": r["decision_comment"] or "", "employee_name": r["employee_name"],
             "label": summary(r)["vendor"] or r["filename"], "amount_label": summary(r)["amount_label"]}
            for r in decided[:8]],
        "by_auditor": [{"name": k, "count": n} for k, n in by_auditor.most_common(10)],
        "recent_blocks": [{"id": b["id"], "ts": b["ts"], "user_name": b["user_name"], "filename": b["filename"],
                           "original_id": b["original_id"], "reason": b["reason"]} for b in blocks[:8]],
    }


# ------------------------------------------------------------------ reports per person
def _value(policy: dict, r: sqlite3.Row) -> float | None:
    """A submission's amount in the policy currency (None when unreadable or in a currency without a rate)."""
    if r["amount_policy"] is not None:
        return r["amount_policy"]
    if r["amount"] is None:
        return None
    rate = rules_engine.fx_rate(policy, r["currency"])
    return round(r["amount"] * rate, 2) if rate else None


def _months_back(n: int) -> list[str]:
    today = datetime.now(timezone.utc).date()
    y, m, out = today.year, today.month, []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def report(policy: dict, user_id: int | None = None, months: int = 6) -> dict:
    """Spending by month, category and vendor for one person (or for everyone when user_id is None)."""
    con = _db()
    q, args = "SELECT * FROM submissions", []
    if user_id is not None:
        q += " WHERE user_id=?"
        args.append(user_id)
    rows = con.execute(q + " ORDER BY id", args).fetchall()
    con.close()

    span = _months_back(max(1, min(months, 24)))
    monthly = {m: {"count": 0, "amount": 0.0, "cleared": 0.0, "in_review": 0.0, "rejected": 0.0} for m in span}
    categories: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": 0.0})
    vendors: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": 0.0})
    totals = Counter()
    money = Counter()
    for r in rows:
        res = json.loads(r["result_json"] or "{}")
        state, value = outcome(r), _value(policy, r) or 0.0
        totals["count"] += 1
        totals[r["status"]] += 1
        totals[state] += 1
        money["amount"] += value
        money[state] += value
        m = monthly.get(r["ts"][:7])
        if m:
            m["count"] += 1
            m["amount"] += value
            m[state] += value
        cat = rules_engine.normalize_category(policy, res.get("category")) or (res.get("category") or "").strip()
        c = categories[cat or "—"]
        c["count"] += 1
        c["amount"] += value
        if res.get("vendor"):
            v = vendors[res["vendor"]]
            v["count"] += 1
            v["amount"] += value

    def ranked(d: dict, key: str, top: int) -> list[dict]:
        items = sorted(d.items(), key=lambda kv: (-kv[1]["amount"], -kv[1]["count"], kv[0]))[:top]
        return [{key: k, "count": v["count"], "amount": round(v["amount"], 2)} for k, v in items]

    return {
        "policy_currency": policy.get("currency", "AZN"),
        "totals": {k: totals[k] for k in ("count", "approved", "flagged", "needs_review", "in_review", "cleared",
                                          "rejected")},
        "money": {k: round(money[k], 2) for k in ("amount", "cleared", "in_review", "rejected")},
        "months": [{"month": k, "count": v["count"], **{x: round(v[x], 2) for x in
                                                          ("amount", "cleared", "in_review", "rejected")}}
                   for k, v in monthly.items()],
        "by_category": ranked(categories, "category", 8),
        "top_vendors": ranked(vendors, "vendor", 5),
    }


def people(policy: dict, users: list[dict]) -> list[dict]:
    """Every account with what it has submitted, for the audit team's list of employees."""
    con = _db()
    rows = con.execute("SELECT * FROM submissions ORDER BY id").fetchall()
    con.close()
    stats: dict[int, dict] = defaultdict(lambda: {"count": 0, "amount": 0.0, "flagged": 0, "rejected": 0,
                                                  "in_review": 0, "last_submission": None})
    for r in rows:
        if r["user_id"] is None:
            continue
        p = stats[r["user_id"]]
        p["count"] += 1
        p["amount"] += _value(policy, r) or 0.0
        p["flagged"] += r["status"] == "flagged"
        p["rejected"] += r["decision"] == "rejected"
        p["in_review"] += outcome(r) == "in_review"
        p["last_submission"] = r["ts"]
    out = []
    for u in users:
        p = stats[u["id"]]
        out.append({"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "active": u["active"],
                    **p, "amount": round(p["amount"], 2)})
    return sorted(out, key=lambda x: (-x["count"], x["name"].lower()))


# ------------------------------------------------------------------ export
def _cell(v) -> str:
    """Spreadsheet-safe text: a cell that starts like a formula is quoted so it is not executed."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") and not isinstance(v, (int, float)) else s


def export_csv(policy: dict) -> str:
    """Every submission as one row, for the accounting system or a spreadsheet."""
    pol_cur = policy.get("currency", "AZN")
    con = _db()
    rows = con.execute("SELECT * FROM submissions ORDER BY id").fetchall()
    con.close()
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["id", "submitted_at", "employee", "employee_email", "vendor", "invoice_number", "invoice_date",
                "category", "amount", "currency", f"amount_{pol_cur.lower()}", "policy_verdict", "rules_broken",
                "outcome", "decided_by", "decided_at", "decision_comment", "file", "sha256"])
    for r in rows:
        res = json.loads(r["result_json"] or "{}")
        w.writerow([_cell(x) for x in (
            r["id"], r["ts"], r["employee_name"], r["employee_email"], res.get("vendor"), res.get("invoice_number"),
            res.get("date"), res.get("category"), r["amount"], r["currency"], r["amount_policy"], r["status"],
            " ".join(v["rule_id"] for v in res.get("violations", [])), outcome(r), r["reviewer"], r["decided_at"],
            r["decision_comment"], r["filename"], r["sha256"])])
    return out.getvalue()
