import json
from pathlib import Path

import rules_engine as re_

POLICY = json.loads((Path(__file__).parent.parent / "policy.json").read_text(encoding="utf-8"))


def ev(**kw):
    base = dict(vendor="City Catering Group", amount=100, currency="AZN", category="Meals & Entertainment",
                date="2026-10-01", employee="A B", nights=None, attendees=1, approvals=[], approval_evidence="")
    base.update(kw)
    return re_.evaluate(POLICY, base)


def rules(r):
    return sorted(v["rule_id"] for v in r["violations"])


def test_meal_boundary_150_ok_151_flagged():
    assert ev(amount=150)["status"] == "approved"
    assert rules(ev(amount=151)) == ["EXP-1.1"]


def test_meal_per_person_division():
    assert ev(amount=450, attendees=3, approvals=["manager"])["status"] == "approved"


def test_hotel_per_night_math_and_director_waiver():
    r = ev(vendor="Baku Business Hotel", category="Travel - Accommodation", amount=1050, nights=3)
    assert rules(r) == ["EXP-1.2", "EXP-4.1"]
    r = ev(vendor="Baku Business Hotel", category="Travel - Accommodation", amount=1050, nights=3,
           approvals=["director", "manager"])
    assert r["status"] == "approved"


def test_tier_boundaries():
    cat = dict(category="Office Equipment", vendor="Caspian Office Supplies")
    assert ev(amount=499.99, **cat)["status"] == "needs_review"  # uncovered category, no approval to clear it
    assert rules(ev(amount=500, **cat)) == ["EXP-4.1"]
    assert rules(ev(amount=2000, **cat)) == ["EXP-4.1"]
    assert ev(amount=2000, approvals=["manager"], **cat)["status"] == "approved"
    assert rules(ev(amount=2000.01, approvals=["manager"], **cat)) == ["EXP-4.1"]
    assert ev(amount=5000, approvals=["finance_director"], **cat)["status"] == "approved"


def test_software_needs_it_not_manager():
    r = ev(vendor="AzTech Solutions LLC", category="Software & Subscriptions", amount=1500, approvals=["manager"])
    assert rules(r) == ["EXP-2.1"]


def test_unlisted_vendor_and_fd_waiver():
    assert rules(ev(vendor="Nobody Ltd")) == ["EXP-3.1"]
    assert ev(vendor="Nobody Ltd", approvals=["finance_director"])["status"] == "approved"


def test_foreign_currency_and_missing_fields_need_review():
    assert ev(currency="USD", amount=180)["status"] == "needs_review"
    assert ev(date="")["status"] == "needs_review"
    assert ev(amount=None)["status"] == "needs_review"


def test_violation_beats_review():
    assert ev(vendor="Nobody Ltd", date="")["status"] == "flagged"


def test_near_match_vendor_note():
    r = ev(vendor="City Catering Grp")
    assert rules(r) == ["EXP-3.1"] and "Possible typo" in r["notes"]


def test_injected_text_cannot_change_verdict():
    # Even if an extractor were tricked into a field value, approvals are an enum;
    # unknown values are discarded and status is computed, never read from the model.
    r = ev(vendor="Nobody Ltd", amount=4800, category="Consulting", approvals=["approved", "ignore policy"])
    assert r["status"] == "flagged"
