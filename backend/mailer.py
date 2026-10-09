"""
Email notifications.

The employee who submitted an invoice gets an email when it is cleared to pay
(automatically by the policy check, or by an auditor) and when an auditor
rejects it. Sending is optional: with no mail settings nothing is sent and
nothing fails.

Two ways to send, chosen by what is configured in backend/.env:

1. An HTTPS mail API (Brevo). Works everywhere, including hosts that block the
   mail ports, such as Render's free web services (ports 25, 465 and 587).
       BREVO_API_KEY=...             # brevo.com > SMTP & API > API keys
       MAIL_FROM=you@gmail.com       # a sender address verified in Brevo

2. SMTP. Fine on your own machine and on hosts that allow the mail ports.
       SMTP_HOST=smtp.gmail.com
       SMTP_PORT=587                 # 587 = STARTTLS, 465 = TLS from the start
       SMTP_USER=you@gmail.com
       SMTP_PASSWORD=...             # for Gmail: an app password, never the account password

   MAIL_FROM_NAME (or SMTP_FROM_NAME) sets the display name, "FiscalAI" by default.

A message is sent on a background thread, so a slow or unreachable mail server
never delays the auditor's click; the outcome is written into the invoice's
history, and a failure never undoes a decision.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import threading
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger("ledger.mail")
TIMEOUT = 15
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _settings() -> dict | None:
    name = (os.environ.get("MAIL_FROM_NAME") or os.environ.get("SMTP_FROM_NAME") or "").strip() or "FiscalAI"
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    sender = (os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER") or "").strip()
    if api_key and sender:
        return {"via": "api", "api_key": api_key, "from": sender, "from_name": name}
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
    return {"via": "smtp", "host": host, "port": port, "user": user, "password": password,
            "from": sender or user, "from_name": name}


def configured() -> bool:
    return _settings() is not None


def status() -> dict:
    """What the admin needs to know about mail, without any secret."""
    cfg = _settings()
    if not cfg:
        return {"configured": False, "via": None, "from": None, "detail": None}
    detail = "Brevo HTTPS API" if cfg["via"] == "api" else f"SMTP {cfg['host']}:{cfg['port']}"
    return {"configured": True, "via": cfg["via"], "from": cfg["from"], "detail": detail}


def _explain(e: Exception, cfg: dict) -> str:
    """A reason a person can act on."""
    text = str(e) or e.__class__.__name__
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return "The mail server refused the user name or password. For Gmail use an app password."
    if isinstance(e, (TimeoutError, OSError)) and cfg["via"] == "smtp" and not isinstance(e, smtplib.SMTPException):
        return (f"Could not reach {cfg['host']}:{cfg['port']} ({text}). Some hosts block the mail ports "
                f"(Render's free plan blocks 25, 465 and 587): set BREVO_API_KEY and MAIL_FROM to send over HTTPS.")
    return text[:300]


def deliver(to: str, subject: str, body: str) -> str | None:
    """Send one plain-text email now. Returns None when the mail service accepted it, otherwise the reason."""
    cfg = _settings()
    to = (to or "").strip()
    if not cfg:
        return "Mail is not configured."
    if "@" not in to:
        return "The recipient has no email address."
    try:
        if cfg["via"] == "api":
            payload = json.dumps({"sender": {"name": cfg["from_name"], "email": cfg["from"]},
                                  "to": [{"email": to}], "subject": subject, "textContent": body}).encode()
            req = urllib.request.Request(BREVO_URL, data=payload, headers={
                "api-key": cfg["api_key"], "Content-Type": "application/json", "Accept": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=TIMEOUT).read()
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:200]
                raise RuntimeError(f"The mail API answered {e.code}: {detail}") from None
        else:
            msg = EmailMessage()
            msg["From"] = formataddr((cfg["from_name"], cfg["from"]))
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)
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
        return None
    except Exception as e:  # noqa: BLE001 - a mail problem must never undo or block a decision
        reason = _explain(e, cfg)
        log.error("Mail to %s could not be sent: %s", to, reason)
        return reason


def send(to: str, subject: str, body: str) -> bool:
    return deliver(to, subject, body) is None


def send_async(to: str, subject: str, body: str, done=None) -> None:
    """Send in the background. `done(error)` is called afterwards with None or the reason it failed."""
    if not configured():
        return

    def work():
        error = deliver(to, subject, body)
        if done:
            try:
                done(error)
            except Exception:  # noqa: BLE001
                log.exception("Could not record the outcome of a mail to %s", to)

    threading.Thread(target=work, daemon=True).start()


def _link() -> str:
    return os.environ.get("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/") + "/my"


def _amount(sub: dict) -> str:
    amount = sub.get("amount_label") or ""
    conv = sub.get("conversion")
    return amount + (f" = {conv['converted']:g} {conv['to']}" if conv else "")


def decision_message(sub: dict) -> tuple[str, str]:
    """Subject and text for the employee whose invoice an auditor just decided. Azerbaijani first, then English."""
    cleared = sub.get("decision") == "approved"
    what = sub.get("vendor") or sub.get("filename") or "invoice"
    amount, who = _amount(sub), sub.get("reviewer") or "auditor"
    comment = (sub.get("decision_comment") or "").strip()
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
    lines += [f"Ətraflı: {_link()}", "", "—", "",
              f"Your invoice #{sub['id']} ({what}, {amount}) was "
              + ("cleared to pay." if cleared else "rejected."),
              f"Decided by: {who}"]
    if comment:
        lines.append(f"Comment: {comment}")
    if not cleared:
        lines.append("Fix what was asked and you can submit it again.")
    lines += [f"Details: {_link()}", "", "FiscalAI"]
    return subject, "\n".join(lines)


def auto_cleared_message(sub: dict) -> tuple[str, str]:
    """For an invoice the policy check approved by itself: no auditor was needed."""
    what = sub.get("vendor") or sub.get("filename") or "invoice"
    amount = _amount(sub)
    subject = f"Faktura #{sub['id']} təsdiqləndi / Invoice #{sub['id']} approved"
    return subject, "\n".join([
        f"Salam, {sub.get('employee_name') or ''}".rstrip(", ") + ",",
        "",
        f"#{sub['id']} nömrəli fakturanız ({what}, {amount}) xərc siyasətinə uyğundur və avtomatik təsdiqləndi. "
        f"Ödəniş üçün Maliyyəyə ötürüldü.",
        f"Ətraflı: {_link()}", "", "—", "",
        f"Your invoice #{sub['id']} ({what}, {amount}) follows the expense policy and was approved automatically. "
        f"It has been passed to Finance for payment.",
        f"Details: {_link()}", "", "FiscalAI"])


def notify_decision(sub: dict | None, done=None) -> None:
    """Tell the employee about the auditor's decision on their invoice."""
    if not sub or not sub.get("decision") or not sub.get("employee_email"):
        return
    send_async(sub["employee_email"], *decision_message(sub), done=done)


def notify_auto_cleared(sub: dict | None, done=None) -> None:
    """Tell the employee their invoice passed the policy check and needs nobody's decision."""
    if not sub or not sub.get("employee_email"):
        return
    send_async(sub["employee_email"], *auto_cleared_message(sub), done=done)
