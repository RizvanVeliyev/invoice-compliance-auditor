"""The assistant answers from the policy and the rules engine, in three languages, and never leaks or decides."""
import assistant


def ask(client, text, lang="en"):
    r = client.post("/api/chat", json={"message": text, "lang": lang})
    assert r.status_code == 200, r.text
    return r.json()["text"]


def test_assistant_needs_a_session_and_a_question(client, as_):
    assert client.post("/api/chat", json={"message": "hello"}).status_code == 401
    as_("employee")
    assert client.post("/api/chat", json={"message": "   "}).status_code == 400
    hello = client.post("/api/chat", json={"message": "salam", "lang": "az"}).json()
    assert "Salam, Murad" in hello["text"] and hello["source"] == "rules" and len(hello["suggestions"]) == 4


def test_policy_questions_in_three_languages(client, as_):
    as_("employee")
    assert "300 AZN" in ask(client, "what is the hotel limit?") and "EXP-1.2" in ask(client, "otel limiti nədir", "az")
    assert "150 AZN" in ask(client, "лимит на обед", "ru") and "EXP-1.1" in ask(client, "лимит на обед", "ru")
    assert "1,000 AZN" in ask(client, "proqram üçün qayda", "az")
    tiers = ask(client, "kimin təsdiqi lazımdır", "az")
    assert "500" in tiers and "2,000" in tiers and "Maliyyə Direktoru" in tiers
    cur = ask(client, "hansı valyutalar qəbul olunur", "az")
    assert "AZN, USD, EUR" in cur and "1 USD = 1.7 AZN" in cur and "1 EUR = 2 AZN" in cur
    assert "City Catering Group" in ask(client, "approved vendors") and "тот же файл" in ask(client, "дубликат", "ru")
    vendors = ask(client, "Təsdiqlənmiş satıcılar", "az")
    assert "NovaCloud Hosting" in vendors and "EXP-4.1" not in vendors          # no stray approval-tier line
    everything = ask(client, "what are the rules")
    assert all(x in everything for x in ("EXP-1.1", "EXP-1.2", "EXP-2.1", "EXP-3.1", "EXP-4.1"))


def test_what_if_uses_the_real_engine(client, as_):
    as_("employee")
    hotel = ask(client, "otel 900 AZN 2 gecə", "az")
    assert "Gecəsi 450 AZN" in hotel and "EXP-1.2 pozulur" in hotel and "Menecer" in hotel
    assert "within the limit of 300" in ask(client, "hotel 560 AZN 2 nights")
    usd = ask(client, "software 650 USD")
    assert "1,105 AZN" in usd and "1.7" in usd and "EXP-2.1" in usd and "Manager" in usd      # looks small, is not
    ru = ask(client, "ПО 650 USD", "ru")
    assert "ПО:" in ru and "EXP-2.1" in ru and "менеджер" in ru                               # the Russian abbreviation
    assert "EXP-2.1" not in ask(client, "software 500 USD")                                   # 850 AZN: no IT approval
    eur = ask(client, "ужин 100 EUR 4 человека", "ru")
    assert "200 AZN" in eur and "50 AZN на человека" in eur and "не требуется" in eur
    meal = ask(client, "lunch 180 azn")
    assert "breaks EXP-1.1" in meal and "assumed 1 person" in meal
    assert "Finance Director" in ask(client, "do I need approval for 2500 AZN")
    assert "Manager" in ask(client, "approval for 2000 azn") and "No approval" in ask(client, "approval for 499 azn")
    assert "GBP" not in ask(client, "hotel 100 gbp")           # an unknown currency word is simply not a currency


def test_own_invoices_only(client, as_, submit):
    as_("employee")
    assert "haven\'t submitted" in ask(client, "my invoices")
    mine = submit("2-hotel-over-limit.pdf").json()["id"]
    as_("auditor")
    theirs = submit("7-software-in-dollars.pdf").json()["id"]
    client.post(f"/api/submissions/{mine}/decision", json={"decision": "rejected", "comment": "Over 300/night"})
    queue = ask(client, "queue")
    assert "Audit desk: 1 open, of them 1 flagged" in queue and "1 decided out of 2" in queue
    assert "NovaCloud" in ask(client, f"#{theirs}") and "Baku Business Hotel" in ask(client, f"invoice {mine}")

    as_("employee")
    why = ask(client, f"#{mine} niyə rədd edildi", "az")
    assert "rədd edilib" in why and "EXP-1.2" in why and "Gunel Auditor" in why and "Over 300/night" in why
    assert ask(client, f"#{theirs}") == f"You have no invoice #{theirs}."      # a colleague's invoice: same answer as a missing one
    assert ask(client, "#9999") == "You have no invoice #9999."
    summary = ask(client, "fakturalarım", "az")
    assert "1 fakturanız var" in summary and "1,140 AZN" in summary and "1 rədd edilib" in summary
    assert "Audit desk" not in ask(client, "queue")            # the queue is for the audit team


def test_unknown_questions_and_the_rate_limit(client, as_, monkeypatch):
    as_("employee")
    r = client.post("/api/chat", json={"message": "tell me a joke", "lang": "xx"}).json()
    assert "not sure" in r["text"] and r["source"] == "rules"                  # no model configured: honest fallback
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setattr(assistant, "_ask_model", lambda *a: "From the model.")
    assert client.post("/api/chat", json={"message": "tell me a joke"}).json() == {
        "text": "From the model.", "source": "model", "suggestions": r["suggestions"]}
    assert client.post("/api/chat", json={"message": "hotel limit"}).json()["source"] == "rules"   # code answers first
    monkeypatch.setattr(assistant, "PER_MINUTE", 2)
    monkeypatch.setattr(assistant, "_recent", {})
    ask(client, "hi "), ask(client, "hi ")
    assert "Too many" in ask(client, "hi ")
