"""Sign-in, roles and account management."""
import sqlite3

import auth
import service
from conftest import PASSWORD

ANON_BLOCKED = [("get", "/api/employees"), ("get", "/api/employees/1"), ("get", "/api/my/report"),
                ("get", "/api/submissions"), ("get", "/api/alerts/summary"), ("get", "/api/overview"),
                ("get", "/api/my/submissions"), ("get", "/api/users"), ("get", "/api/audit-log"),
                ("get", "/api/submissions/1"), ("get", "/api/submissions/1/file")]


def test_nothing_private_is_reachable_without_signing_in(client, submit):
    for method, path in ANON_BLOCKED:
        assert getattr(client, method)(path).status_code == 401, path
    assert submit("1-team-lunch-approved.pdf").status_code == 401
    assert client.post("/api/analyze", json={"invoice_text": "Vendor: X"}).status_code == 401
    assert client.post("/api/submissions/1/decision", json={"decision": "approved"}).status_code == 401
    assert client.get("/api/policy").status_code == 200 and client.get("/api/health").status_code == 200


def test_roles_limit_what_each_account_can_reach(client, as_, submit):
    as_("employee")
    for path in ("/api/submissions", "/api/alerts/summary", "/api/overview", "/api/users", "/api/audit-log",
                 "/api/employees", "/api/employees/1", "/api/export.csv"):
        assert client.get(path).status_code == 403, path
    sid = submit("2-hotel-over-limit.pdf").json()["id"]
    assert client.post(f"/api/submissions/{sid}/decision", json={"decision": "approved"}).status_code == 403
    assert client.post(f"/api/submissions/{sid}/reopen", json={"text": "x"}).status_code == 403
    assert client.post(f"/api/submissions/{sid}/notes", json={"text": "x"}).status_code == 403
    assert client.get("/api/my/report").status_code == 200
    as_("auditor")
    assert client.get("/api/submissions").status_code == 200 and client.get("/api/overview").status_code == 200
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/users", json={"email": "x@y.zz", "name": "X", "role": "employee",
                                           "password": PASSWORD}).status_code == 403
    as_("admin")
    assert client.get("/api/users").status_code == 200 and client.get("/api/submissions").status_code == 200


def test_login_logout_and_session_cookie(client, as_):
    assert client.get("/api/auth/state").json() == {"user": None, "setup_required": False}
    bad = client.post("/api/auth/login", json={"email": "murad@nordvik.test", "password": "wrong-password"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@nordvik.test", "password": "wrong-password"})
    assert bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json()   # no account probing
    r = client.post("/api/auth/login", json={"email": " MURAD@nordvik.test ", "password": PASSWORD})
    assert r.status_code == 200 and "password" not in r.text
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/auth/state").json()["user"]["role"] == "employee"
    token = client.cookies.get(auth.SESSION_COOKIE)
    client.post("/api/auth/logout")
    client.cookies.set(auth.SESSION_COOKIE, token)              # a copied cookie is dead after sign-out
    assert client.get("/api/my/submissions").status_code == 401


def test_passwords_and_tokens_are_not_stored_in_the_clear(client, as_):
    as_("employee")
    token = client.cookies.get(auth.SESSION_COOKIE)
    dump = "\n".join(sqlite3.connect(service.DB_PATH).iterdump())
    assert PASSWORD not in dump and token not in dump and "scrypt$" in dump


def test_repeated_wrong_passwords_lock_the_email_briefly(client):
    wrong = {"email": "murad@nordvik.test", "password": "wrong-password"}
    for _ in range(auth.MAX_FAILS):
        assert client.post("/api/auth/login", json=wrong).status_code == 401
    r = client.post("/api/auth/login", json={"email": "murad@nordvik.test", "password": PASSWORD})
    assert r.status_code == 401 and "Too many" in r.json()["detail"]


def test_admin_creates_changes_and_deactivates_accounts(client, as_):
    as_("admin")
    new = {"email": "Nigar@Nordvik.test", "name": "Nigar Aliyeva", "role": "employee", "password": "first-pass-1"}
    made = client.post("/api/users", json=new).json()
    assert made["email"] == "nigar@nordvik.test" and made["active"] is True and "password_hash" not in made
    assert "already exists" in client.post("/api/users", json=new).json()["detail"]
    for bad in ({**new, "email": "not-an-email"}, {**new, "email": "a@b.cc", "password": "short"},
                {**new, "email": "a@b.cc", "role": "owner"}, {**new, "email": "a@b.cc", "name": " "}):
        assert client.post("/api/users", json=bad).status_code == 400, bad

    as_("nigar@nordvik.test", "first-pass-1")
    nigar_token = client.cookies.get(auth.SESSION_COOKIE)
    assert client.get("/api/submissions").status_code == 403

    as_("admin")
    uid = made["id"]
    assert client.patch(f"/api/users/{uid}", json={"role": "auditor", "name": "Nigar A."}).json()["role"] == "auditor"
    client.cookies.set(auth.SESSION_COOKIE, nigar_token)        # her open session picks the new role up at once
    assert client.get("/api/auth/state").json()["user"]["role"] == "auditor"
    assert client.get("/api/submissions").status_code == 200

    as_("admin")
    client.patch(f"/api/users/{uid}", json={"password": "reset-pass-22"})
    assert client.post("/api/auth/login", json={"email": new["email"], "password": "first-pass-1"}).status_code == 401
    as_("nigar@nordvik.test", "reset-pass-22")
    nigar_token = client.cookies.get(auth.SESSION_COOKIE)

    as_("admin")
    assert client.patch(f"/api/users/{uid}", json={"active": False}).json()["active"] is False
    client.cookies.set(auth.SESSION_COOKIE, nigar_token)
    assert client.get("/api/my/submissions").status_code == 401             # open session ended
    client.cookies.clear()
    assert client.post("/api/auth/login",
                       json={"email": new["email"], "password": "reset-pass-22"}).status_code == 401
    as_("admin")
    assert client.patch("/api/users/9999", json={"name": "Ghost"}).status_code == 404


def test_there_is_exactly_one_admin(client, as_):
    me = as_("admin")
    assert client.patch(f"/api/users/{me['id']}", json={"active": False}).status_code == 400
    assert client.patch(f"/api/users/{me['id']}", json={"role": "auditor"}).status_code == 400
    assert client.patch(f"/api/users/{me['id']}", json={"name": "Farid A."}).json()["name"] == "Farid A."
    extra = client.post("/api/users", json={"email": "b@nordvik.test", "name": "Second Admin", "role": "admin",
                                            "password": PASSWORD})
    assert extra.status_code == 400 and "single admin" in extra.json()["detail"]
    auditor = next(u for u in client.get("/api/users").json() if u["role"] == "auditor")
    promote = client.patch(f"/api/users/{auditor['id']}", json={"role": "admin"})
    assert promote.status_code == 400 and "single admin" in promote.json()["detail"]
    assert [u["role"] for u in client.get("/api/users").json()].count("admin") == 1


def test_anyone_can_register_as_employee_or_auditor_but_never_as_admin(client):
    body = {"name": "Nigar Aliyeva", "email": "Nigar@Nordvik.test", "password": "first-pass-1"}
    made = client.post("/api/auth/register", json={**body, "role": "employee"})
    assert made.status_code == 200 and made.json()["role"] == "employee" and "password" not in made.text
    assert client.get("/api/my/submissions").status_code == 200             # signed in straight away
    assert client.get("/api/submissions").status_code == 403                # an employee, not an auditor
    assert "already exists" in client.post("/api/auth/register", json={**body, "role": "auditor"}).json()["detail"]

    client.cookies.clear()
    client.cookies.clear()
    for bad in ({"role": "admin"}, {"role": "owner"}, {"password": "short"}, {"email": "nope"}, {"name": " "}):
        r = client.post("/api/auth/register", json={**body, "email": "x@nordvik.test", "role": "employee", **bad})
        assert r.status_code == 400, bad
    assert client.get("/api/auth/state").json()["user"] is None             # a refused sign-up signs nobody in
    plain = client.post("/api/auth/register", json={**body, "email": "y@nordvik.test"})    # role left out
    assert plain.json()["role"] == "employee"


def test_changing_your_own_password(client, as_):
    as_("employee")
    other_device = client.cookies.get(auth.SESSION_COOKIE)
    as_("employee")
    body = {"current_password": "wrong-password", "new_password": "brand-new-pass"}
    assert client.post("/api/auth/password", json=body).status_code == 400
    assert client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "x"}).status_code == 400
    assert client.post("/api/auth/password", json={**body, "current_password": PASSWORD}).status_code == 200
    assert client.get("/api/my/submissions").status_code == 200             # this session stays
    client.cookies.set(auth.SESSION_COOKIE, other_device)
    assert client.get("/api/my/submissions").status_code == 401             # the other one does not
    as_("employee", "brand-new-pass")


def test_first_run_setup_creates_the_only_admin_once(client, monkeypatch, tmp_path):
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "fresh.db")
    assert client.get("/api/auth/state").json() == {"user": None, "setup_required": True}
    # People may have registered before the admin exists; setup is still open until there is one.
    client.post("/api/auth/register", json={"name": "Early Bird", "email": "early@nordvik.test",
                                            "password": PASSWORD, "role": "auditor"})
    client.cookies.clear()
    assert client.get("/api/auth/state").json()["setup_required"] is True
    body = {"email": "boss@nordvik.test", "name": "First Admin", "password": PASSWORD}
    made = client.post("/api/auth/setup", json=body)
    assert made.status_code == 200 and made.json()["role"] == "admin"
    assert client.get("/api/users").status_code == 200                      # signed in straight away
    again = client.post("/api/auth/setup", json={**body, "email": "intruder@nordvik.test"})
    assert again.status_code == 400
    assert [u["role"] for u in auth.list_users()].count("admin") == 1


def test_admin_can_be_seeded_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "seed.db")
    monkeypatch.setattr(auth, "SCRYPT_N", 2 ** 8)
    monkeypatch.setenv("ADMIN_EMAIL", "Root@Nordvik.test")
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    auth.seed_admin_from_env()
    auth.seed_admin_from_env()                                              # second start: nothing new
    users = auth.list_users()
    assert [(u["email"], u["role"]) for u in users] == [("root@nordvik.test", "admin")]
    assert auth.authenticate("root@nordvik.test", PASSWORD)["id"] == users[0]["id"]
    monkeypatch.setenv("ADMIN_EMAIL", "other@nordvik.test")
    auth.seed_admin_from_env()                                              # a changed setting renames the one admin
    assert [(u["email"], u["role"]) for u in auth.list_users()] == [("other@nordvik.test", "admin")]


def test_auditor_cannot_decide_on_their_own_invoice(client, as_, submit):
    as_("auditor")
    sid = submit("2-hotel-over-limit.pdf").json()["id"]
    r = client.post(f"/api/submissions/{sid}/decision", json={"decision": "approved"})
    assert r.status_code == 403 and "another auditor" in r.json()["detail"]
    as_("admin")
    assert client.post(f"/api/submissions/{sid}/decision", json={"decision": "approved"}).status_code == 200


def test_registering_as_auditor_gives_auditor_access_at_once(client):
    body = {"name": "Leyla Mammadova", "email": "leyla@nordvik.test", "password": "first-pass-1", "role": "auditor"}
    me = client.post("/api/auth/register", json=body).json()
    assert (me["role"], me["requested_role"]) == ("auditor", None)
    assert client.get("/api/submissions").status_code == 200 and client.get("/api/overview").status_code == 200
    assert client.get("/api/users").status_code == 403                      # accounts stay with the admin
    assert client.get("/api/health").json()["auditor_signup"] == "open"
    client.cookies.clear()
    back = client.post("/api/auth/login", json={"email": body["email"], "password": body["password"]}).json()
    assert back["role"] == "auditor"                                        # and signs in as one


def test_with_approval_switched_on_an_auditor_waits_for_the_admin(client, as_, submit, monkeypatch):
    monkeypatch.setenv("AUDITOR_SIGNUP", "approval")
    body = {"name": "Leyla Mammadova", "email": "leyla@nordvik.test", "password": "first-pass-1", "role": "auditor"}
    me = client.post("/api/auth/register", json=body).json()
    assert (me["role"], me["requested_role"]) == ("employee", "auditor")
    assert client.get("/api/submissions").status_code == 403                # not an auditor yet...
    assert client.post("/api/submissions/1/decision", json={"decision": "approved"}).status_code == 403
    assert submit("1-team-lunch-approved.pdf").status_code == 200           # ...but can already submit
    leyla = client.cookies.get(auth.SESSION_COOKIE)

    as_("admin")
    assert client.get("/api/users/pending").json() == {"pending": 1}
    assert client.get("/api/users").json()[0]["email"] == "leyla@nordvik.test"     # requests are listed first
    approved = client.patch(f"/api/users/{me['id']}", json={"role": "auditor"}).json()
    assert (approved["role"], approved["requested_role"]) == ("auditor", None)
    assert client.get("/api/users/pending").json() == {"pending": 0}

    client.cookies.set(auth.SESSION_COOKIE, leyla)                          # no need to sign in again
    assert client.get("/api/submissions").status_code == 200 and client.get("/api/overview").status_code == 200
    assert client.get("/api/users").status_code == 403                      # accounts stay with the admin


def test_admin_can_decline_an_auditor_request(client, as_, monkeypatch):
    monkeypatch.setenv("AUDITOR_SIGNUP", "approval")
    body = {"name": "Rauf Hajiyev", "email": "rauf@nordvik.test", "password": "first-pass-1", "role": "auditor"}
    me = client.post("/api/auth/register", json=body).json()
    as_("admin")
    declined = client.patch(f"/api/users/{me['id']}", json={"decline_request": True}).json()
    assert (declined["role"], declined["requested_role"], declined["active"]) == ("employee", None, True)
    as_("rauf@nordvik.test", "first-pass-1")
    assert client.get("/api/submissions").status_code == 403


def test_ready_made_auditor_can_be_seeded_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "seed.db")
    monkeypatch.setattr(auth, "SCRYPT_N", 2 ** 8)
    monkeypatch.setenv("AUDITOR_EMAIL", "Audit@Nordvik.test")
    monkeypatch.setenv("AUDITOR_PASSWORD", PASSWORD)
    auth.seed_auditor_from_env()
    auth.seed_auditor_from_env()                                            # second start: nothing new
    assert [(u["email"], u["role"]) for u in auth.list_users()] == [("audit@nordvik.test", "auditor")]


def test_a_fresh_install_has_the_built_in_admin(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "fresh.db")
    monkeypatch.setattr(auth, "SCRYPT_N", 2 ** 8)
    monkeypatch.setattr(auth, "_fails", {})
    for name in ("ADMIN_EMAIL", "ADMIN_PASSWORD", "ADMIN_NAME", "DEFAULT_ADMIN"):
        monkeypatch.delenv(name, raising=False)
    auth.seed_admin_from_env()
    auth.seed_admin_from_env()                                              # second start: still one admin
    assert [(u["email"], u["role"]) for u in auth.list_users()] == [("admin@fiscalai.local", "admin")]
    assert auth.authenticate("admin@fiscalai.local", "FiscalAI-Admin-2026")["name"] == "FiscalAI Admin"


def test_your_own_admin_settings_replace_the_built_in_one(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "own.db")
    monkeypatch.setattr(auth, "SCRYPT_N", 2 ** 8)
    monkeypatch.setenv("ADMIN_EMAIL", "boss@nordvik.test")
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    auth.seed_admin_from_env()
    assert [u["email"] for u in auth.list_users()] == ["boss@nordvik.test"]   # the published default never exists here

    monkeypatch.setattr(service, "DB_PATH", tmp_path / "off.db")
    monkeypatch.delenv("ADMIN_EMAIL"), monkeypatch.delenv("ADMIN_PASSWORD")
    monkeypatch.setenv("DEFAULT_ADMIN", "off")
    auth.seed_admin_from_env()
    assert auth.list_users() == [] and auth.has_admin() is False            # back to the one-time setup form


def test_the_sign_in_side_must_match_the_account(client, monkeypatch):
    def login(who, side):
        client.cookies.clear()
        r = client.post("/api/auth/login", json={"email": who, "password": PASSWORD, "side": side})
        return r.status_code, client.get("/api/auth/state").json()["user"]

    code, user = login("murad@nordvik.test", "auditor")              # an employee on the Audit team tab
    assert code == 403 and user is None                              # refused, and no session was started
    assert client.get("/api/submissions").status_code == 401
    code, user = login("auditor@nordvik.test", "employee")           # an auditor on the Employee tab
    assert code == 403 and user is None

    assert login("murad@nordvik.test", "employee")[1]["role"] == "employee"
    assert login("auditor@nordvik.test", "auditor")[1]["role"] == "auditor"
    assert login("admin@nordvik.test", "employee")[1]["role"] == "admin"      # the admin signs in on either side
    assert login("admin@nordvik.test", "auditor")[1]["role"] == "admin"
    assert login("murad@nordvik.test", "boss")[0] == 400

    # A wrong password is still a wrong password, whatever the side: the side is never checked first.
    client.cookies.clear()
    bad = client.post("/api/auth/login", json={"email": "murad@nordvik.test", "password": "wrong-password", "side": "auditor"})
    assert bad.status_code == 401

    # Someone still waiting for the admin's approval is told so, and signs in as an employee meanwhile.
    monkeypatch.setenv("AUDITOR_SIGNUP", "approval")
    client.cookies.clear()
    client.post("/api/auth/register", json={"name": "Leyla M", "email": "leyla@nordvik.test", "password": PASSWORD, "role": "auditor"})
    client.cookies.clear()
    waiting = client.post("/api/auth/login", json={"email": "leyla@nordvik.test", "password": PASSWORD, "side": "auditor"})
    assert waiting.status_code == 403 and "not approved yet" in waiting.json()["detail"]
    assert login("leyla@nordvik.test", "employee")[0] == 200


def test_the_configured_admin_always_works_after_a_restart(monkeypatch, tmp_path):
    """An old database, a forgotten password, a deactivated or demoted admin: a restart repairs all of them."""
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "old.db")
    monkeypatch.setattr(auth, "SCRYPT_N", 2 ** 8)
    monkeypatch.setattr(auth, "_fails", {})
    for name in ("ADMIN_EMAIL", "ADMIN_PASSWORD", "ADMIN_NAME", "DEFAULT_ADMIN"):
        monkeypatch.delenv(name, raising=False)
    old = auth.create_user("someone@old.test", "Old Admin", "admin", "an-old-password")     # made by the old setup form
    emp = auth.create_user("murad@nordvik.test", "Murad", "employee", PASSWORD)

    auth.seed_admin_from_env()                                              # a restart with no admin settings
    me = auth.authenticate("admin@fiscalai.local", "FiscalAI-Admin-2026")
    assert me["id"] == old["id"] and me["role"] == "admin"                  # the same single admin, now reachable
    assert [u["role"] for u in auth.list_users()].count("admin") == 1
    assert auth.get_user(emp["id"])["role"] == "employee"                   # nobody else is touched

    con = auth._db()
    with con:
        con.execute("UPDATE users SET active=0, password_hash=? WHERE id=?", ("broken", old["id"]))
    con.close()
    auth.seed_admin_from_env()
    assert auth.authenticate("admin@fiscalai.local", "FiscalAI-Admin-2026")["active"] is True

    monkeypatch.setenv("ADMIN_EMAIL", "boss@nordvik.test")                  # the host now sets its own admin
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    auth.seed_admin_from_env()
    assert auth.authenticate("boss@nordvik.test", PASSWORD)["id"] == old["id"]
    try:
        auth.authenticate("admin@fiscalai.local", "FiscalAI-Admin-2026")
    except auth.AuthError:
        pass
    else:
        raise AssertionError("the published default still worked after the host set its own admin")


def test_the_admin_address_cannot_be_registered(client, monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    r = client.post("/api/auth/register", json={"name": "Sneaky", "email": "Admin@FiscalAI.local",
                                                "password": "first-pass-1", "role": "employee"})
    assert r.status_code == 400 and "reserved for the admin" in r.json()["detail"]
