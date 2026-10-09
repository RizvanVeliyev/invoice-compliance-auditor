"""
Employee submissions and auditor alerts.

Flow:
  employee uploads an invoice PDF (or photo)  ->  file is validated and stored
  -> service.analyze() (AI extraction + deterministic rules)  ->  submission row
  -> if the result needs attention, an alert appears on the auditor desk
     (and is optionally pushed to a webhook such as Slack / Teams / Discord).

A submission is never lost: if the document cannot be read automatically it is
stored as needs_review and the auditor is alerted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import service

log = logging.getLogger("ledger.submissions")

ALLOWED = {
    "application/pdf": (b"%PDF-", ".pdf"),
    "image/png": (b"\x89PNG", ".png"),
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
    "image/webp": (b"RIFF", ".webp"),
}
DECISIONS = {"approved", "rejected"}


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


# ------------------------------------------------------------------ checks around the AI verdict
def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"\w+", (s or "").lower()) if len(t) >= 3}


def submission_warnings(con, name: str, sha: str, result: dict) -> list[str]:
    warnings = []
    extracted = result.get("employee") or ""
    if extracted and name and not (_tokens(extracted) & _tokens(name)):
        warnings.append(f"Submitted by '{name}', but the invoice names '{extracted}' as the employee.")
    prev = con.execute("SELECT id, employee_name, ts FROM submissions WHERE sha256=? ORDER BY id",
                       (sha,)).fetchall()
    for p in prev[:3]:
        warnings.append(f"This exact file was already submitted as #{p['id']} by {p['employee_name']} "
                        f"on {p['ts'][:10]}.")
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
        "vendor": "", "amount": None, "currency": "", "category": "", "date": "", "employee": "",
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
def create(policy: dict, data: bytes, declared_mime: str, filename: str,
           employee_name: str, employee_email: str = "", note: str = "") -> dict:
    name = (employee_name or "").strip()
    if not name:
        raise ValueError("Enter your name so the audit team knows who submitted the invoice.")
    mime = sniff_mime(data, declared_mime, filename)
    sha = hashlib.sha256(data).hexdigest()
    stored = f"{uuid.uuid4().hex}{ALLOWED[mime][1]}"
    (_uploads_dir() / stored).write_bytes(data)

    try:
        result = service.analyze(policy, file_bytes=data, mime=mime)
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

    con = _db()
    warnings = list(result.get("history_warnings") or []) + submission_warnings(con, name, sha, result)
    result["history_warnings"] = warnings
    status = result["status"]
    alert = status != "approved" or bool(warnings)
    with con:
        cur = con.execute(
            "INSERT INTO submissions (ts, employee_name, employee_email, note, filename, stored_name, mime, size,"
            " sha256, status, alert, warnings_json, result_json, review_state) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_now(), name[:120], (employee_email or "").strip()[:200], (note or "").strip()[:1000],
             (filename or "invoice")[:200], stored, mime, len(data), sha, status, int(alert),
             json.dumps(warnings), json.dumps(result), "new" if alert else "auto_cleared"),
        )
        sid = cur.lastrowid
    row = summary(con.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone())
    con.close()
    if alert:
        _notify(row)

    return {
        "id": sid,
        "status": status,
        "sent_to_audit": alert,
        "message": employee_message(status, alert),
        "vendor": result.get("vendor"), "amount": result.get("amount"), "currency": result.get("currency"),
        "category": result.get("category"), "date": result.get("date"), "employee": result.get("employee"),
        "violations": [{"rule_id": v["rule_id"], "explanation": v["explanation"], "severity": v["severity"]}
                       for v in result.get("violations", [])],
        "review_reasons": result.get("needs_review_reasons", []),
        "warnings": warnings,
        "meta": result.get("meta", {}),
    }


def summary(r: sqlite3.Row) -> dict:
    res = json.loads(r["result_json"] or "{}")
    amt, cur = res.get("amount"), res.get("currency") or ""
    return {
        "id": r["id"], "ts": r["ts"], "employee_name": r["employee_name"], "employee_email": r["employee_email"],
        "filename": r["filename"], "status": r["status"], "alert": bool(r["alert"]),
        "review_state": r["review_state"], "decision": r["decision"],
        "vendor": res.get("vendor") or "", "amount": amt, "currency": cur,
        "amount_label": (f"{amt:,.0f} {cur}" if amt == int(amt) else f"{amt:,.2f} {cur}").strip()
        if isinstance(amt, (int, float)) else "amount unreadable",
        "category": res.get("category") or "",
        "violation_ids": [v["rule_id"] for v in res.get("violations", [])],
        "warning_count": len(json.loads(r["warnings_json"] or "[]")),
    }


def list_(status: str | None = None, state: str | None = None, limit: int = 100) -> list[dict]:
    q, args = "SELECT * FROM submissions WHERE 1=1", []
    if status:
        q += " AND status=?"
        args.append(status)
    if state == "open":
        q += " AND alert=1 AND decision IS NULL"
    elif state == "decided":
        q += " AND decision IS NOT NULL"
    q += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(limit, 500)))
    con = _db()
    rows = [summary(r) for r in con.execute(q, args).fetchall()]
    con.close()
    return rows


def get(sid: int) -> dict | None:
    con = _db()
    r = con.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    con.close()
    if not r:
        return None
    out = summary(r)
    out.update(note=r["note"], mime=r["mime"], size=r["size"], sha256=r["sha256"],
               decision_comment=r["decision_comment"], reviewer=r["reviewer"], decided_at=r["decided_at"],
               warnings=json.loads(r["warnings_json"] or "[]"), result=json.loads(r["result_json"] or "{}"))
    return out


def file_path(sid: int) -> tuple[Path, str, str] | None:
    con = _db()
    r = con.execute("SELECT stored_name, mime, filename FROM submissions WHERE id=?", (sid,)).fetchone()
    con.close()
    if not r:
        return None
    p = _uploads_dir() / r["stored_name"]
    return (p, r["mime"], r["filename"]) if p.exists() else None


def mark_seen(sid: int) -> None:
    con = _db()
    with con:
        con.execute("UPDATE submissions SET review_state='seen' WHERE id=? AND review_state='new'", (sid,))
    con.close()


def decide(sid: int, decision: str, comment: str = "", reviewer: str = "") -> dict | None:
    if decision not in DECISIONS:
        raise ValueError("Decision must be 'approved' or 'rejected'.")
    if decision == "rejected" and not (comment or "").strip():
        raise ValueError("Add a short reason when rejecting, so the employee knows what to fix.")
    con = _db()
    with con:
        n = con.execute(
            "UPDATE submissions SET decision=?, decision_comment=?, reviewer=?, decided_at=?, review_state='decided'"
            " WHERE id=?", (decision, (comment or "").strip()[:1000], (reviewer or "").strip()[:120], _now(), sid)
        ).rowcount
    con.close()
    return get(sid) if n else None


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
