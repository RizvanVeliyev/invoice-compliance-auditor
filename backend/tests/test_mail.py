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
    # Send inline, so the test can look at the message and at what was written into the history.
    monkeypatch.setattr(mailer, "send_async",
                        lambda to, s, b, done=None: (lambda e: done(e) if done else None)(mailer.deliver(to, s, b)))


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


def test_automatic_approval_is_emailed_and_the_history_says_so(client, as_, submit, monkeypatch):
    mail_on(monkeypatch)
    client.post("/api/auth/register", json={"name": "Aysel Karimova", "email": "aysel@nordvik.test",
                                            "password": "first-pass-1", "role": "employee"})
    clean = submit("1-team-lunch-approved.pdf").json()             # named on the invoice: approved, no alert
    assert clean["sent_to_audit"] is False
    assert [m["To"] for m in FakeSMTP.sent] == ["aysel@nordvik.test"]
    body = FakeSMTP.sent[0].get_content()
    assert "approved automatically" in body and "avtomatik təsdiqləndi" in body and "390 AZN" in body
    flagged = submit("2-hotel-over-limit.pdf").json()              # goes to an auditor: no mail until they decide
    assert len(FakeSMTP.sent) == 1

    events = client.get("/api/my/submissions").json()
    assert [e["kind"] for e in next(s for s in events if s["id"] == clean["id"])["events"]] == ["submitted", "email"]

    as_("auditor")
    client.post(f"/api/submissions/{flagged['id']}/decision", json={"decision": "rejected", "comment": "No"})
    kinds = [(e["kind"], e["user_name"], e["text"]) for e in client.get(f"/api/submissions/{flagged['id']}").json()["events"]]
    assert kinds[-1] == ("email", "FiscalAI", "aysel@nordvik.test") and len(FakeSMTP.sent) == 2


def test_a_failed_mail_is_recorded_for_the_audit_team_only(client, as_, submit, monkeypatch):
    as_("employee")
    sid = submit("2-hotel-over-limit.pdf").json()["id"]
    mail_on(monkeypatch)

    class Blocked:
        def __init__(self, *a, **k):
            raise TimeoutError("timed out")

    monkeypatch.setattr(mailer.smtplib, "SMTP", Blocked)
    as_("auditor")
    done = client.post(f"/api/submissions/{sid}/decision", json={"decision": "approved"})
    assert done.status_code == 200
    last = client.get(f"/api/submissions/{sid}").json()["events"][-1]
    assert last["kind"] == "email_failed" and "murad@nordvik.test" in last["text"]
    assert "BREVO_API_KEY" in last["text"] and "block" in last["text"]          # says what to do about it
    as_("employee")
    assert "email_failed" not in [e["kind"] for e in client.get("/api/my/submissions").json()[0]["events"]]


def test_https_mail_api_is_used_when_configured(client, as_, monkeypatch):
    calls = []

    class Answer:
        def read(self):
            return b'{"messageId": "1"}'

    def fake_urlopen(req, timeout=None):
        calls.append((req.full_url, dict(req.header_items()), req.data))
        return Answer()

    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("MAIL_FROM", "sender@example.com")
    monkeypatch.setattr(mailer.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mailer.smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(AssertionError("SMTP used")))
    assert mailer.status() == {"configured": True, "via": "api", "from": "sender@example.com", "detail": "Brevo HTTPS API"}
    assert mailer.deliver("murad@nordvik.test", "Hello", "Body") is None
    url, headers, data = calls[0]
    assert url == "https://api.brevo.com/v3/smtp/email" and headers["Api-key"] == "xkeysib-test"
    import json
    sent = json.loads(data)
    assert sent["sender"]["email"] == "sender@example.com" and sent["to"] == [{"email": "murad@nordvik.test"}]
    assert sent["subject"] == "Hello" and sent["textContent"] == "Body"

    as_("auditor")
    assert client.get("/api/mail").status_code == 403 and client.post("/api/mail/test", json={"to": "a@b.cc"}).status_code == 403
    as_("admin")
    assert client.get("/api/mail").json()["via"] == "api"
    assert client.post("/api/mail/test", json={"to": "a@b.cc"}).json()["ok"] is True and len(calls) == 2
    monkeypatch.delenv("BREVO_API_KEY")
    off = client.post("/api/mail/test", json={"to": "a@b.cc"}).json()
    assert off["ok"] is False and off["configured"] is False and "not configured" in off["error"]
