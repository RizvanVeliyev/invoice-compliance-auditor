"""The employee is emailed when an auditor decides on their invoice."""
import mailer


class FakeSMTP:
    sent: list = []
    calls: list = []

    def __init__(self, host, port, timeout=None, context=None):
        FakeSMTP.calls.append(("connect", host, port))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        FakeSMTP.calls.append(("starttls",))

    def login(self, user, password):
        FakeSMTP.calls.append(("login", user, password))

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def mail_on(monkeypatch):
    FakeSMTP.sent, FakeSMTP.calls = [], []
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("APP_PUBLIC_URL", "https://fiscal.example")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer, "send_async", mailer.send)        # send inline so the test can look


def test_employee_is_emailed_when_their_invoice_is_cleared_or_rejected(client, as_, submit, monkeypatch):
    as_("employee")
    hotel = submit("2-hotel-over-limit.pdf").json()["id"]
    usd = submit("7-software-in-dollars.pdf").json()["id"]
    mail_on(monkeypatch)
    assert FakeSMTP.sent == []                                     # submitting sends nothing

    as_("auditor")
    client.post(f"/api/submissions/{usd}/decision", json={"decision": "approved", "comment": "IT confirmed"})
    client.post(f"/api/submissions/{hotel}/decision", json={"decision": "rejected", "comment": "Over 300/night"})
    assert [m["To"] for m in FakeSMTP.sent] == ["murad@nordvik.test", "murad@nordvik.test"]
    assert ("connect", "smtp.gmail.com", 587) in FakeSMTP.calls and ("starttls",) in FakeSMTP.calls
    assert ("login", "sender@example.com", "abcdefghijklmnop") in FakeSMTP.calls   # spaces dropped

    ok, no = FakeSMTP.sent
    assert f"#{usd}" in ok["Subject"] and "cleared to pay" in ok["Subject"] and "FiscalAI" in ok["From"]
    body = ok.get_content()
    assert "NovaCloud Hosting" in body and "650 USD = 1105 AZN" in body and "Gunel Auditor" in body
    assert "IT confirmed" in body and "https://fiscal.example/my" in body and "ödənişə buraxıldı" in body
    assert "rejected" in no["Subject"] and "Over 300/night" in no.get_content()
    assert "yenidən göndərə bilərsiniz" in no.get_content()

    # Notes and reopening are internal steps: no email.
    client.post(f"/api/submissions/{hotel}/notes", json={"text": "internal"})
    as_("admin")
    client.post(f"/api/submissions/{hotel}/reopen", json={"text": "new information"})
    assert len(FakeSMTP.sent) == 2
    client.post(f"/api/submissions/{hotel}/decision", json={"decision": "approved"})
    assert len(FakeSMTP.sent) == 3                                 # the new decision is announced


def test_no_mail_settings_or_a_broken_server_never_blocks_a_decision(client, as_, submit, monkeypatch):
    as_("employee")
    sid = submit("2-hotel-over-limit.pdf").json()["id"]
    as_("auditor")
    assert mailer.configured() is False and mailer.send("a@b.cc", "s", "b") is False
    assert client.post(f"/api/submissions/{sid}/decision", json={"decision": "rejected", "comment": "x"}).status_code == 200

    mail_on(monkeypatch)

    class Down:
        def __init__(self, *a, **k):
            raise OSError("connection refused")

    monkeypatch.setattr(mailer.smtplib, "SMTP", Down)
    as_("admin")
    client.post(f"/api/submissions/{sid}/reopen", json={"text": "again"})
    r = client.post(f"/api/submissions/{sid}/decision", json={"decision": "approved"})
    assert r.status_code == 200 and r.json()["decision"] == "approved"
