"""Employee PDF submission -> AI/rules verdict -> auditor alert -> decision."""
import service


def text_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with a real text layer, built in memory."""
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for line in lines:
        c.drawString(50, y, line)
        y -= 18
    c.save()
    return buf.getvalue()


def record(vendor="City Catering Group", amount="120 AZN", date="2026-10-06", number="CCG-1", extra=()):
    return text_pdf(["EXPENSE RECORD", f"Invoice No: {number}" if number else "", f"Vendor: {vendor}",
                     f"Date: {date}", "Employee: Murad Quliyev", "Category: Meals & Entertainment",
                     "Description: Lunch, single attendee", f"Amount: {amount}", "Approval: None stated", *extra])


def test_clean_pdf_is_approved_without_alert(client, as_, submit):
    as_("employee")
    r = submit("1-team-lunch-approved.pdf").json()
    assert r["status"] == "approved"
    # Sent under Murad's account but the invoice names Aysel: approved, yet the auditor is told.
    assert r["sent_to_audit"] is True and any("names 'Aysel Karimova'" in w for w in r["warnings"])
    as_("auditor")
    row = client.get("/api/submissions").json()[0]
    assert row["employee_name"] == "Murad Quliyev" and row["employee_email"] == "murad@nordvik.test"


def test_flagged_pdf_alerts_auditor_and_can_be_decided(client, as_, submit):
    as_("employee")
    r = submit("2-hotel-over-limit.pdf").json()
    assert r["status"] == "flagged" and [v["rule_id"] for v in r["violations"]] == ["EXP-1.2"]
    assert r["sent_to_audit"] and "audit team" in r["message"]
    as_("auditor")
    s = client.get("/api/alerts/summary").json()
    assert s["unread"] == 1 and s["flagged"] == 1
    queue = client.get("/api/submissions?state=open").json()
    assert queue[0]["id"] == r["id"] and queue[0]["amount_label"] == "1,140 AZN"
    detail = client.get(f"/api/submissions/{r['id']}").json()
    assert detail["result"]["trace"] and detail["employee_email"] == "murad@nordvik.test"
    assert client.get("/api/alerts/summary").json()["unread"] == 0          # opened -> seen
    f = client.get(f"/api/submissions/{r['id']}/file")
    assert f.status_code == 200 and f.content.startswith(b"%PDF-")
    assert client.post(f"/api/submissions/{r['id']}/decision", json={"decision": "rejected"}).status_code == 400
    d = client.post(f"/api/submissions/{r['id']}/decision",
                    json={"decision": "rejected", "comment": "Book under 300/night"}).json()
    assert d["decision"] == "rejected" and d["reviewer"] == "Gunel Auditor"   # taken from the session
    assert client.get("/api/alerts/summary").json()["open"] == 0


def test_scanned_pdf_without_vision_model_still_reaches_a_person(as_, submit):
    as_("employee")
    r = submit("5-scanned-receipt-needs-ai.pdf").json()
    assert r["status"] == "needs_review" and r["sent_to_audit"]
    assert "could not be read" in r["review_reasons"][0]


def test_injection_pdf_flagged_and_reported(as_, submit):
    as_("employee")
    r = submit("4-forged-approval-note.pdf").json()
    assert r["status"] == "flagged" and any("automated reviewer" in x for x in r["review_reasons"])


def test_rejects_non_pdf_bytes_even_if_labelled_pdf(as_, submit):
    as_("employee")
    r = submit("fake.pdf", data=b"MZ\x90\x00 not a pdf")
    assert r.status_code == 400 and "Only PDF" in r.json()["detail"]


def test_sample_pdf_listing_and_path_safety(client):
    names = [s["name"] for s in client.get("/api/sample-pdfs").json()]
    assert "2-hotel-over-limit.pdf" in names and "7-software-in-dollars.pdf" in names
    assert client.get("/api/sample-pdfs/2-hotel-over-limit.pdf").status_code == 200
    assert client.get("/api/sample-pdfs/..%2Fpolicy.json").status_code == 404


# ------------------------------------------------------------------ currencies
def test_usd_and_eur_invoices_are_converted(as_, submit):
    as_("employee")
    usd = submit("7-software-in-dollars.pdf").json()
    assert (usd["amount"], usd["currency"], usd["amount_policy"]) == (650, "USD", 1105)
    assert usd["conversion"]["rate"] == 1.7
    assert sorted(v["rule_id"] for v in usd["violations"]) == ["EXP-2.1", "EXP-4.1"]   # 650 looked harmless
    eur = submit("6-hotel-in-euro.pdf").json()
    assert (eur["amount"], eur["currency"], eur["amount_policy"]) == (280, "EUR", 560)
    assert eur["status"] == "approved"                                                  # 280 AZN per night


def test_selected_currency_fills_in_only_when_the_invoice_shows_none(client, as_, submit):
    as_("employee")
    bare = submit("bare.pdf", data=record(amount="100", number="B-1"), currency="USD").json()
    assert (bare["currency"], bare["amount_policy"]) == ("USD", 170) and bare["violations"][0]["rule_id"] == "EXP-1.1"
    printed = submit("printed.pdf", data=record(amount="100 EUR", number="B-2"), currency="USD").json()
    assert printed["currency"] == "EUR" and any("selected USD" in w for w in printed["warnings"])
    assert submit("x.pdf", data=record(number="B-3"), currency="GBP").status_code == 400
    as_("auditor")
    detail = client.get(f"/api/submissions/{bare['id']}").json()["result"]
    assert any("selected by the submitter" in a for a in detail["assumptions"])


# ------------------------------------------------------------------ duplicates are refused
def test_same_file_is_refused_for_everyone(client, as_, submit):
    as_("employee")
    first = submit("2-hotel-over-limit.pdf").json()
    again = submit("2-hotel-over-limit.pdf")
    assert again.status_code == 409 and f"#{first['id']}" in again.json()["detail"]
    assert "by you" in again.json()["detail"]
    as_("auditor")
    other = submit("2-hotel-over-limit.pdf")
    assert other.status_code == 409 and "by a colleague" in other.json()["detail"]
    assert "Murad" not in other.json()["detail"]                    # no names leaked to the second sender
    assert client.get("/api/alerts/summary").json()["total"] == 1   # nothing extra was stored
    o = client.get("/api/overview").json()
    assert o["counts"]["duplicates_blocked"] == 2 and o["recent_blocks"][0]["user_name"] == "Gunel Auditor"


def test_same_invoice_in_a_different_file_is_refused(as_, submit):
    as_("employee")
    assert submit("a.pdf", data=record(number="CCG-77")).status_code == 200
    # Re-export of the same invoice: other bytes, even another total, same vendor + number.
    rescan = submit("a-rescan.pdf", data=record(number="ccg-77", amount="125 AZN", extra=["scanned copy"]))
    assert rescan.status_code == 409 and "invoice number" in rescan.json()["detail"]
    # No number printed anywhere: vendor + amount + currency + date decides.
    assert submit("b.pdf", data=record(number="", amount="90 AZN")).status_code == 200
    copy = submit("b-copy.pdf", data=record(number="", amount="90 AZN", extra=["copy"]))
    assert copy.status_code == 409 and "same vendor, amount (90 AZN) and date" in copy.json()["detail"]


def test_different_invoices_are_not_mistaken_for_duplicates(as_, submit):
    as_("employee")
    assert submit("a.pdf", data=record(number="CCG-1", amount="90 AZN")).status_code == 200
    assert submit("b.pdf", data=record(number="CCG-2", amount="90 AZN")).status_code == 200   # two numbers
    assert submit("c.pdf", data=record(number="", amount="90 AZN", date="2026-10-07")).status_code == 200
    assert submit("d.pdf", data=record(number="", amount="90 USD", date="2026-10-07")).status_code == 200
    assert submit("e.pdf", data=record(number="", amount="90 AZN", date="2026-10-07",
                                       vendor="SkyLine Travel Agency")).status_code == 200


def test_rejected_invoice_can_be_sent_again(client, as_, submit):
    as_("employee")
    first = submit("2-hotel-over-limit.pdf").json()
    as_("auditor")
    client.post(f"/api/submissions/{first['id']}/decision", json={"decision": "rejected", "comment": "Fix it"})
    as_("employee")
    again = submit("2-hotel-over-limit.pdf")
    assert again.status_code == 200
    assert any(f"submitted before as #{first['id']}" in w and "rejected" in w for w in again.json()["warnings"])


def test_duplicate_is_caught_before_the_model_is_called(as_, submit, monkeypatch):
    as_("employee")
    submit("2-hotel-over-limit.pdf")
    monkeypatch.setattr(service, "analyze", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    assert submit("2-hotel-over-limit.pdf").status_code == 409


# ------------------------------------------------------------------ following progress
def test_employee_follows_their_own_invoices_only(client, as_, submit):
    as_("employee")
    mine = submit("2-hotel-over-limit.pdf").json()
    as_("auditor")
    theirs = submit("7-software-in-dollars.pdf").json()
    as_("employee")
    rows = client.get("/api/my/submissions").json()
    assert [r["id"] for r in rows] == [mine["id"]] and rows[0]["outcome"] == "in_review"
    assert rows[0]["violations"][0]["rule_id"] == "EXP-1.2"
    assert client.get(f"/api/submissions/{mine['id']}/file").status_code == 200
    assert client.get(f"/api/submissions/{theirs['id']}/file").status_code == 404
    as_("auditor")
    client.post(f"/api/submissions/{mine['id']}/decision", json={"decision": "rejected", "comment": "Too dear"})
    as_("employee")
    row = client.get("/api/my/submissions").json()[0]
    assert (row["outcome"], row["decision_comment"], row["reviewer"]) == ("rejected", "Too dear", "Gunel Auditor")


def test_overview_adds_everything_up_in_azn(client, as_, submit):
    as_("employee")
    submit("6-hotel-in-euro.pdf")             # 280 EUR = 560 AZN, approved but name mismatch -> in review
    hotel = submit("2-hotel-over-limit.pdf").json()     # 1140 AZN flagged
    submit("7-software-in-dollars.pdf")       # 650 USD = 1105 AZN flagged
    submit("5-scanned-receipt-needs-ai.pdf")  # unreadable
    as_("auditor")
    client.post(f"/api/submissions/{hotel['id']}/decision", json={"decision": "rejected", "comment": "No"})
    o = client.get("/api/overview").json()
    assert o["counts"] | {} == {"total": 4, "approved": 1, "flagged": 2, "needs_review": 1, "in_review": 3,
                                "cleared": 0, "auto_cleared": 0, "rejected": 1, "duplicates_blocked": 0}
    assert o["money"] == {"submitted": 2805.0, "cleared": 0.0, "in_review": 1665.0, "rejected": 1140.0}
    assert {c["currency"]: (c["count"], c["amount"], c["amount_policy"]) for c in o["by_currency"]} == {
        "AZN": (1, 1140.0, 1140.0), "USD": (1, 650.0, 1105.0), "EUR": (1, 280.0, 560.0)}
    assert {r["rule_id"]: r["count"] for r in o["by_rule"]} == {"EXP-1.2": 1, "EXP-2.1": 1, "EXP-4.1": 1}
    assert o["by_employee"][0] == {"name": "Murad Quliyev", "count": 4, "flagged": 2, "rejected": 1,
                                   "amount_policy": 2805.0}
    assert len(o["by_day"]) == 14 and sum(d["flagged"] for d in o["by_day"]) == 2
    assert o["decisions"] == 1 and o["avg_decision_hours"] is not None


def test_overview_lists_decisions_and_export_is_spreadsheet_safe(client, as_, submit):
    as_("employee")
    hotel = submit("2-hotel-over-limit.pdf").json()
    submit("7-software-in-dollars.pdf")
    evil = submit("evil.pdf", data=record(vendor="=HYPERLINK(1)", number="E-1")).json()
    assert client.get("/api/export.csv").status_code == 403                 # auditors only
    as_("auditor")
    client.post(f"/api/submissions/{hotel['id']}/decision", json={"decision": "rejected", "comment": "Too dear"})
    o = client.get("/api/overview").json()
    assert o["by_auditor"] == [{"name": "Gunel Auditor", "count": 1}]
    assert o["recent_decisions"][0] | {"decided_at": ""} == {
        "id": hotel["id"], "decided_at": "", "reviewer": "Gunel Auditor", "decision": "rejected",
        "comment": "Too dear", "employee_name": "Murad Quliyev", "label": "Baku Business Hotel",
        "amount_label": "1,140 AZN"}

    r = client.get("/api/export.csv")
    assert r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 3
    first = rows[0]
    assert (first["vendor"], first["amount"], first["currency"], first["amount_azn"]) == (
        "Baku Business Hotel", "1140.0", "AZN", "1140.0")
    assert (first["policy_verdict"], first["rules_broken"], first["outcome"], first["decided_by"]) == (
        "flagged", "EXP-1.2", "rejected", "Gunel Auditor")
    assert (rows[1]["amount"], rows[1]["currency"], rows[1]["amount_azn"]) == ("650.0", "USD", "1105.0")
    assert rows[2]["id"] == str(evil["id"]) and rows[2]["vendor"] == "\'=HYPERLINK(1)"
