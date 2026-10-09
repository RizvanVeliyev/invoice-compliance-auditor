"""Employee PDF submission -> AI/rules verdict -> auditor alert -> decision."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
import service

PDFS = Path(__file__).parent.parent / "sample_pdfs"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "audit.db")
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    monkeypatch.delenv("AUDITOR_PIN", raising=False)
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    return TestClient(main.app)


def submit(client, name, who="Murad Quliyev", data=None, mime="application/pdf"):
    data = data if data is not None else (PDFS / name).read_bytes()
    return client.post("/api/submissions", files={"file": (name, data, mime)},
                       data={"employee_name": who, "employee_email": "m@example.com", "note": "Baku trip"})


def test_clean_pdf_is_approved_without_alert(client):
    r = submit(client, "1-team-lunch-approved.pdf", who="Aysel Karimova").json()
    assert r["status"] == "approved" and r["sent_to_audit"] is False
    assert client.get("/api/alerts/summary").json()["unread"] == 0


def test_flagged_pdf_alerts_auditor_and_can_be_decided(client):
    r = submit(client, "2-hotel-over-limit.pdf").json()
    assert r["status"] == "flagged" and [v["rule_id"] for v in r["violations"]] == ["EXP-1.2"]
    assert r["sent_to_audit"] and "audit team" in r["message"]
    s = client.get("/api/alerts/summary").json()
    assert s["unread"] == 1 and s["flagged"] == 1
    queue = client.get("/api/submissions?state=open").json()
    assert queue[0]["id"] == r["id"] and queue[0]["amount_label"] == "1,140 AZN"
    detail = client.get(f"/api/submissions/{r['id']}").json()
    assert detail["result"]["trace"] and detail["employee_email"] == "m@example.com"
    assert client.get("/api/alerts/summary").json()["unread"] == 0          # opened -> seen
    f = client.get(f"/api/submissions/{r['id']}/file")
    assert f.status_code == 200 and f.content.startswith(b"%PDF-")
    assert client.post(f"/api/submissions/{r['id']}/decision", json={"decision": "rejected"}).status_code == 400
    d = client.post(f"/api/submissions/{r['id']}/decision",
                    json={"decision": "rejected", "comment": "Book under 300/night", "reviewer": "FD"}).json()
    assert d["decision"] == "rejected" and client.get("/api/alerts/summary").json()["open"] == 0


def test_scanned_pdf_without_vision_model_still_reaches_a_person(client):
    r = submit(client, "5-scanned-receipt-needs-ai.pdf", who="Leyla Mammadova").json()
    assert r["status"] == "needs_review" and r["sent_to_audit"]
    assert "could not be read" in r["review_reasons"][0]


def test_injection_pdf_flagged_and_reported(client):
    r = submit(client, "4-forged-approval-note.pdf", who="Rauf Hajiyev").json()
    assert r["status"] == "flagged" and any("automated reviewer" in x for x in r["review_reasons"])


def test_name_mismatch_and_resubmitted_file_warn(client):
    submit(client, "1-team-lunch-approved.pdf", who="Aysel Karimova")
    r = submit(client, "1-team-lunch-approved.pdf", who="Someone Else").json()
    assert any("names 'Aysel Karimova'" in w for w in r["warnings"])
    assert any("already submitted as #1" in w for w in r["warnings"])
    assert r["sent_to_audit"] is True                     # approved, but warnings still alert the auditor


def test_rejects_non_pdf_bytes_even_if_labelled_pdf(client):
    r = submit(client, "fake.pdf", data=b"MZ\x90\x00 not a pdf")
    assert r.status_code == 400 and "Only PDF" in r.json()["detail"]
    assert submit(client, "1-team-lunch-approved.pdf", who="  ").status_code == 400


def test_auditor_pin(client, monkeypatch):
    monkeypatch.setenv("AUDITOR_PIN", "4321")
    assert client.get("/api/submissions").status_code == 401
    assert client.get("/api/submissions", headers={"X-Auditor-Pin": "4321"}).status_code == 200
    assert client.get("/api/health").json()["auditor_pin_required"] is True
    assert submit(client, "1-team-lunch-approved.pdf").status_code == 200   # employees never need the PIN


def test_sample_pdf_listing_and_path_safety(client):
    names = [s["name"] for s in client.get("/api/sample-pdfs").json()]
    assert "2-hotel-over-limit.pdf" in names
    assert client.get("/api/sample-pdfs/2-hotel-over-limit.pdf").status_code == 200
    assert client.get("/api/sample-pdfs/..%2Fpolicy.json").status_code == 404
