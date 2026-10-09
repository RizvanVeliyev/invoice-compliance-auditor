"""
Email notifications.

When an auditor clears or rejects an invoice, the employee who submitted it gets
an email. Sending is optional: without SMTP_HOST / SMTP_USER / SMTP_PASSWORD in
the environment nothing is sent and nothing fails.

Settings (backend/.env):
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587                 # 587 = STARTTLS, 465 = TLS from the start
    SMTP_USER=you@gmail.com
    SMTP_PASSWORD=...             # for Gmail: an app password, never the account password
    SMTP_FROM_NAME=FiscalAI       # optional display name

A message is sent on a background thread, so a slow or unreachable mail server
never delays the auditor's click; a failure is logged, and the decision stands.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger("ledger.mail")
TIMEOUT = 15


def _settings() -> dict | None:
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    # Gmail shows app passwords in groups of four; the spaces are not part of the password.
    password = os.environ.get("SMTP_PASSWORD", "").replace(" ", "")
    if not (host and user and password):
        return None
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        port = 587
    return {"host": host, "port": port, "user": user, "password": password,
            "from_name": os.environ.get("SMTP_FROM_NAME", "").strip() or "FiscalAI"}


def configured() -> bool:
    return _settings() is not None


def send(to: str, subject: str, body: str) -> bool:
    """Send one plain-text email now. Returns False (and logs why) instead of raising."""
    cfg = _settings()
    to = (to or "").strip()
    if not cfg or "@" not in to:
        return False
    msg = EmailMessage()
    msg["From"] = formataddr((cfg["from_name"], cfg["user"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        context = ssl.create_default_context()
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=TIMEOUT, context=context) as smtp:
                smtp.login(cfg["user"], cfg["password"])
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=TIMEOUT) as smtp:
                smtp.starttls(context=context)
                smtp.login(cfg["user"], cfg["password"])
                smtp.send_message(msg)
        log.info("Mail sent to %s: %s", to, subject)
        return True
    except Exception:  # noqa: BLE001 - a mail problem must never undo or block a decision
        log.exception("Mail to %s could not be sent", to)
        return False


def send_async(to: str, subject: str, body: str) -> None:
    if configured():
        threading.Thread(target=send, args=(to, subject, body), daemon=True).start()


def decision_message(sub: dict) -> tuple[str, str]:
    """Subject and text for the employee whose invoice was just decided. Azerbaijani first, then English."""
    cleared = sub.get("decision") == "approved"
    what = sub.get("vendor") or sub.get("filename") or "invoice"
    amount = sub.get("amount_label") or ""
    conv = sub.get("conversion")
    if conv:
        amount += f" = {conv['converted']:g} {conv['to']}"
    who = sub.get("reviewer") or "auditor"
    comment = (sub.get("decision_comment") or "").strip()
    link = os.environ.get("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/") + "/my"
    subject = (f"Faktura #{sub['id']} ödənişə buraxıldı" if cleared else f"Faktura #{sub['id']} rədd edildi") + \
              f" / Invoice #{sub['id']} {'cleared to pay' if cleared else 'rejected'}"
    lines = [
        f"Salam, {sub.get('employee_name') or ''}".rstrip(", ") + ",",
        "",
        f"#{sub['id']} nömrəli fakturanız ({what}, {amount}) "
        + ("ödənişə buraxıldı." if cleared else "rədd edildi."),
        f"Qərarı verən: {who}",
    ]
    if comment:
        lines.append(f"Şərh: {comment}")
    if not cleared:
        lines.append("Göstərilən səbəbi düzəldib fakturanı yenidən göndərə bilərsiniz.")
    lines += [f"Ətraflı: {link}", "", "—", "",
              f"Your invoice #{sub['id']} ({what}, {amount}) was "
              + ("cleared to pay." if cleared else "rejected."),
              f"Decided by: {who}"]
    if comment:
        lines.append(f"Comment: {comment}")
    if not cleared:
        lines.append("Fix what was asked and you can submit it again.")
    lines += [f"Details: {link}", "", "FiscalAI"]
    return subject, "\n".join(lines)


def notify_decision(sub: dict | None) -> None:
    """Tell the employee about the decision on their invoice, if mail is set up and they have an address."""
    if not sub or not sub.get("decision") or not sub.get("employee_email"):
        return
    subject, body = decision_message(sub)
    send_async(sub["employee_email"], subject, body)
