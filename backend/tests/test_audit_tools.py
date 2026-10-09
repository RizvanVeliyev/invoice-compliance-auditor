"""What the audit team can do beyond clear / reject: search, notes, reopening, history, reports per person."""
from datetime import datetime, timezone

from test_submissions import record


def test_decision_history_notes_and_reopening(client, as_, submit):
    as_("employee")
    sid = submit("2-hotel-over-limit.pdf").json()["id"]
    as_("auditor")
    assert client.post(f"/api/submissions/{sid}/notes", json={"text": " "}).status_code == 400
    client.post(f"/api/submissions/{sid}/notes", json={"text": "Asked the manager for the booking email"})
    client.post(f"/api/submissions/{sid}/decision", json={"decision": "rejected", "comment": "Over 300/night"})

    # One decision at a time: a second auditor cannot silently overwrite the first.
    as_("admin")
    again = client.post(f"/api/submissions/{sid}/decision", json={"decision": "approved"})
    assert again.status_code == 400 and "Gunel Auditor already decided" in again.json()["detail"]
    assert client.post(f"/api/submissions/{sid}/reopen", json={"text": ""}).status_code == 400    # a reason is needed
    reopened = client.post(f"/api/submissions/{sid}/reopen", json={"text": "Director approval arrived"}).json()
    assert reopened["decision"] is None and reopened["reviewer"] is None
    assert client.get("/api/alerts/summary").json()["open"] == 1                # back in the queue
    assert client.post(f"/api/submissions/{sid}/reopen", json={"text": "again"}).status_code == 400
    final = client.post(f"/api/submissions/{sid}/decision", json={"decision": "approved", "comment": "OK now"}).json()

    assert [(e["kind"], e["user_name"], e["text"]) for e in final["events"]] == [
        ("submitted", "Murad Quliyev", "Baku trip"),
        ("note", "Gunel Auditor", "Asked the manager for the booking email"),
        ("rejected", "Gunel Auditor", "Over 300/night"),
        ("reopened", "Farid Admin", "Director approval arrived"),
        ("approved", "Farid Admin", "OK now"),
    ]
    as_("employee")                 # the employee sees the history of decisions, never the internal notes
    mine = client.get("/api/my/submissions").json()[0]
    assert [e["kind"] for e in mine["events"]] == ["submitted", "rejected", "reopened", "approved"]
    assert mine["outcome"] == "cleared"


def test_auditor_cannot_reopen_their_own_invoice(client, as_, submit):
    as_("auditor")
    sid = submit("2-hotel-over-limit.pdf").json()["id"]
    as_("admin")
    client.post(f"/api/submissions/{sid}/decision", json={"decision": "rejected", "comment": "No"})
    as_("auditor")
    assert client.post(f"/api/submissions/{sid}/reopen", json={"text": "please"}).status_code == 403


def test_search_finds_invoices_by_person_vendor_number_or_id(client, as_, submit):
    as_("employee")
    hotel = submit("2-hotel-over-limit.pdf").json()["id"]
    submit("7-software-in-dollars.pdf")
    as_("auditor")
    submit("3-unlisted-software-vendor.pdf")

    def found(q):
        return sorted(r["vendor"] for r in client.get("/api/submissions", params={"q": q}).json())

    assert found("baku business") == ["Baku Business Hotel"]
    assert found("NOVACLOUD") == ["NovaCloud Hosting"]
    assert found("murad") == ["Baku Business Hotel", "NovaCloud Hosting"]
    assert found("bbh-88310") == ["Baku Business Hotel"]
    assert found(f"#{hotel}") == ["Baku Business Hotel"]
    assert found("pixelforge") == ["Pixelforge Studio LLC"]
    assert found("no such thing") == [] and found("%") == []                  # wildcards are not special
    assert len(client.get("/api/submissions", params={"q": "  "}).json()) == 3
    murad = next(p for p in client.get("/api/employees").json() if p["name"] == "Murad Quliyev")
    assert len(client.get("/api/submissions", params={"user_id": murad["id"]}).json()) == 2


def test_employee_report_by_month_category_and_vendor(client, as_, submit):
    as_("employee")
    hotel = submit("2-hotel-over-limit.pdf").json()["id"]          # 1140 AZN, accommodation
    submit("6-hotel-in-euro.pdf")                                   # 280 EUR = 560 AZN, accommodation
    submit("7-software-in-dollars.pdf")                             # 650 USD = 1105 AZN, software
    submit("lunch.pdf", data=record(amount="90 AZN", number="L-1"))  # meals, auto-cleared
    submit("5-scanned-receipt-needs-ai.pdf")                        # unreadable: counted, no amount
    as_("auditor")
    submit("3-unlisted-software-vendor.pdf")                        # somebody else's, must not leak in
    client.post(f"/api/submissions/{hotel}/decision", json={"decision": "rejected", "comment": "No"})

    as_("employee")
    r = client.get("/api/my/report").json()
    assert r["totals"] == {"count": 5, "approved": 2, "flagged": 2, "needs_review": 1, "in_review": 3,
                           "cleared": 1, "rejected": 1}
    assert r["money"] == {"amount": 2895.0, "cleared": 90.0, "in_review": 1665.0, "rejected": 1140.0}
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    assert len(r["months"]) == 6 and r["months"][-1] == {
        "month": this_month, "count": 5, "amount": 2895.0, "cleared": 90.0, "in_review": 1665.0, "rejected": 1140.0}
    assert all(m["count"] == 0 for m in r["months"][:-1])
    assert r["by_category"][:3] == [
        {"category": "Travel - Accommodation", "count": 2, "amount": 1700.0},
        {"category": "Software & Subscriptions", "count": 1, "amount": 1105.0},
        {"category": "Meals & Entertainment", "count": 1, "amount": 90.0}]
    assert r["top_vendors"][0] == {"vendor": "Baku Business Hotel", "count": 2, "amount": 1700.0}
    assert len(client.get("/api/my/report", params={"months": 12}).json()["months"]) == 12


def test_audit_team_sees_every_person_and_their_report(client, as_, submit):
    as_("employee")
    submit("2-hotel-over-limit.pdf")
    submit("7-software-in-dollars.pdf")
    as_("auditor")
    people = client.get("/api/employees").json()
    assert len(people) == 3 and people[0]["name"] == "Murad Quliyev"            # most invoices first
    assert {k: people[0][k] for k in ("count", "amount", "flagged", "rejected", "in_review", "role")} == {
        "count": 2, "amount": 2245.0, "flagged": 2, "rejected": 0, "in_review": 2, "role": "employee"}
    assert people[1]["count"] == 0 and people[1]["last_submission"] is None
    one = client.get(f"/api/employees/{people[0]['id']}").json()
    assert one["user"]["email"] == "murad@nordvik.test" and "password_hash" not in one["user"]
    assert one["report"]["money"]["amount"] == 2245.0 and len(one["submissions"]) == 2
    assert client.get("/api/employees/9999").status_code == 404


def test_list_can_be_filtered_and_paged(client, as_, submit):
    as_("employee")
    for i in range(7):
        submit(f"l{i}.pdf", data=record(number=f"L-{i}", amount=f"{40 + i} AZN"))
    submit("7-software-in-dollars.pdf")
    submit("6-hotel-in-euro.pdf")
    as_("auditor")

    first = client.get("/api/submissions", params={"page": 1, "page_size": 4})
    assert first.headers["x-total-count"] == "9" and len(first.json()) == 4
    assert [r["id"] for r in first.json()] == [9, 8, 7, 6]                      # newest first
    third = client.get("/api/submissions", params={"page": 3, "page_size": 4})
    assert [r["id"] for r in third.json()] == [1] and third.headers["x-total-count"] == "9"
    assert client.get("/api/submissions", params={"page": 9, "page_size": 4}).json() == []
    assert len(client.get("/api/submissions", params={"page": 0, "page_size": 1000}).json()) == 9   # clamped

    usd = client.get("/api/submissions", params={"currency": "usd", "page": 1})
    assert usd.headers["x-total-count"] == "1" and usd.json()[0]["vendor"] == "NovaCloud Hosting"
    both = client.get("/api/submissions", params={"currency": "AZN", "q": "catering", "page": 2, "page_size": 5})
    assert both.headers["x-total-count"] == "7" and len(both.json()) == 2

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert client.get("/api/submissions", params={"date_from": today, "date_to": today}).headers["x-total-count"] == "9"
    assert client.get("/api/submissions", params={"date_to": "2020-01-01"}).json() == []
    assert client.get("/api/submissions", params={"date_from": "2999-01-01"}).json() == []
    assert len(client.get("/api/submissions", params={"date_from": "not-a-date"}).json()) == 9     # ignored, not an error
    flagged = client.get("/api/submissions", params={"status": "flagged", "state": "open", "page": 1})
    assert flagged.headers["x-total-count"] == "1"
    assert len(client.get("/api/submissions").json()) == 9                     # no paging asked: as before
