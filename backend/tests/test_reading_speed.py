"""Which reader handles an upload when a model is configured, and what happens when the model is down."""
import llm_providers
import service
from test_submissions import text_pdf

FREE_TEXT = ["Hi, attaching the receipt for last night.", "Dinner at City Catering Group with 2 clients,",
             "total came to 240 manat. Rauf (manager) said it is fine.", "Thanks, Murad"]


def model_on(monkeypatch, answer=None, error=None):
    calls = []

    def fake(text, file_bytes=None, mime=None):
        calls.append(text)
        if error:
            raise error
        return answer, {"input_tokens": 800, "output_tokens": 100}

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(llm_providers, "call_gemini", fake)
    return calls


def test_template_documents_are_read_without_calling_the_model(as_, submit, monkeypatch):
    calls = model_on(monkeypatch, error=AssertionError("the model was called"))
    as_("employee")
    r = submit("2-hotel-over-limit.pdf").json()
    assert r["status"] == "flagged" and r["meta"]["provider"] == "offline" and calls == []
    assert r["meta"]["latency_ms"] < 3000 and r["warnings"] == []


def test_free_text_goes_to_the_model(as_, submit, monkeypatch):
    calls = model_on(monkeypatch, answer={
        "vendor": "City Catering Group", "invoice_number": "", "amount": 240, "currency": "AZN",
        "category": "Meals & Entertainment", "date": "2026-10-08", "employee": "Murad Quliyev", "description": "Dinner",
        "nights": None, "attendees": 3, "approvals": [], "approval_evidence": ""})
    as_("employee")
    r = submit("email.pdf", data=text_pdf(FREE_TEXT)).json()
    assert len(calls) == 1 and r["meta"]["provider"] == "gemini" and r["status"] == "approved" and r["amount"] == 240
    monkeypatch.setenv("FAST_TEMPLATE_READ", "off")                 # switch the shortcut off: everything goes to the model
    submit("7-software-in-dollars.pdf")
    assert len(calls) == 2


def test_a_model_that_is_down_does_not_lose_or_block_the_invoice(client, as_, submit, monkeypatch):
    model_on(monkeypatch, error=RuntimeError("503 UNAVAILABLE"))
    as_("employee")
    r = submit("email.pdf", data=text_pdf(FREE_TEXT))
    assert r.status_code == 200                                     # not a 500, not an endless wait
    body = r.json()
    assert body["status"] == "needs_review" and body["sent_to_audit"] and body["meta"]["provider"] == "offline"
    assert any("could not be reached" in w for w in body["warnings"])
    scan = submit("5-scanned-receipt-needs-ai.pdf").json()          # an image has no text to fall back on
    assert scan["status"] == "needs_review" and "could not be read" in scan["review_reasons"][0]


def test_busy_model_is_retried_briefly_then_given_up(monkeypatch):
    class Busy(Exception):
        code = 503

    tries, naps = [], []
    monkeypatch.setattr(llm_providers.time, "sleep", naps.append)

    def call():
        tries.append(1)
        raise Busy("busy")

    try:
        llm_providers._with_retry(call)
    except Busy:
        pass
    assert len(tries) == 2 and naps == [2] and sum(naps) <= 5       # one short wait: a person is waiting
    assert service.TEMPLATE_FIELDS == ("vendor", "amount", "category", "date")
