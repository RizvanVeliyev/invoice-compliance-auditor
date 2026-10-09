"""
Accounts, sessions and roles.

Three roles:
  employee  submits invoices and follows their own submissions
  auditor   everything an employee can do, plus the audit desk (clear / reject)
            and the overview
  admin     everything an auditor can do, plus managing accounts

Employees and auditors register themselves and choose which of the two they
are, and get that role at once. Because an auditor can clear invoices for
payment, a company can require the admin to confirm each auditor instead:
with AUDITOR_SIGNUP=approval a person who registers as an auditor starts with
employee access and a pending request, which the admin approves or declines on
the Accounts page. There is exactly ONE admin account. It is never created by registration:
it comes from ADMIN_EMAIL / ADMIN_PASSWORD in the environment, or from the
one-time setup screen that is only available while no admin exists. Nobody can
be promoted to admin, and the admin cannot be demoted or deactivated.

Passwords are stored as salted scrypt hashes. A session is a random token kept
in an HttpOnly cookie; only its SHA-256 is stored, so a leaked database cannot
be replayed as a login.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import service

log = logging.getLogger("ledger.auth")

ROLES = ("employee", "auditor", "admin")
SIGNUP_ROLES = ("employee", "auditor")        # what a person may choose when registering
AUDIT_ROLES = ("auditor", "admin")
SESSION_COOKIE = "ledger_session"
SESSION_HOURS = 12
MIN_PASSWORD = 8
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1

MAX_FAILS = 5              # wrong passwords in a row before an email is locked
LOCK_SECONDS = 60
_fails: dict[str, tuple[int, float]] = {}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(ValueError):
    """A problem the user can fix (shown as the error message)."""


# ------------------------------------------------------------------ storage
def _db():
    con = service._db()
    con.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, name TEXT, role TEXT,"
        " password_hash TEXT, active INTEGER DEFAULT 1, created_at TEXT, last_login TEXT, requested_role TEXT)"
    )
    if "requested_role" not in {r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()}:
        con.execute("ALTER TABLE users ADD COLUMN requested_role TEXT")
    con.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        " token_sha TEXT PRIMARY KEY, user_id INTEGER, created_at TEXT, expires_at TEXT)"
    )
    con.row_factory = sqlite3.Row
    return con


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def public(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "email": r["email"], "name": r["name"], "role": r["role"],
            "active": bool(r["active"]), "created_at": r["created_at"], "last_login": r["last_login"],
            "requested_role": r["requested_role"]}


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def _clean(email: str, name: str | None, role: str | None, password: str | None) -> tuple[str, str | None]:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 200:
        raise AuthError("Enter a valid email address.")
    if name is not None:
        name = name.strip()
        if not name:
            raise AuthError("Enter the person's name.")
        if len(name) > 120:
            raise AuthError("The name is too long (120 characters at most).")
    if role is not None and role not in ROLES:
        raise AuthError("Role must be employee, auditor or admin.")
    if password is not None:
        check_password(password)
    return email, name


def check_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise AuthError(f"The password must be at least {MIN_PASSWORD} characters.")
    if len(password) > 200:
        raise AuthError("The password is too long (200 characters at most).")


# ------------------------------------------------------------------ accounts
def count_users() -> int:
    con = _db()
    n = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    con.close()
    return n


def create_user(email: str, name: str, role: str, password: str, requested_role: str | None = None) -> dict:
    email, name = _clean(email, name, role, password)
    con = _db()
    try:
        with con:
            cur = con.execute(
                "INSERT INTO users (email, name, role, password_hash, active, created_at, requested_role)"
                " VALUES (?,?,?,?,1,?,?)",
                (email, name, role, hash_password(password), _iso(_now()), requested_role))
        row = con.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        raise AuthError(f"An account for {email} already exists.") from None
    finally:
        con.close()
    return public(row)


def has_admin() -> bool:
    con = _db()
    n = con.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
    con.close()
    return n > 0


def register(email: str, name: str, role: str, password: str) -> dict:
    """Self-registration: an employee or an auditor, never the admin."""
    if role not in SIGNUP_ROLES:
        raise AuthError("Choose whether you are an employee or an auditor.")
    want = configured_admin()
    if (email or "").strip().lower() in {DEFAULT_ADMIN["email"], want["email"] if want else ""}:
        raise AuthError("That address is reserved for the admin. Sign in instead.")
    if role == "auditor" and auditor_signup_needs_approval():
        return create_user(email, name, "employee", password, requested_role="auditor")
    return create_user(email, name, role, password)


def auditor_signup_needs_approval() -> bool:
    return os.environ.get("AUDITOR_SIGNUP", "open").strip().lower() == "approval"


def pending_requests() -> int:
    con = _db()
    n = con.execute("SELECT COUNT(*) FROM users WHERE requested_role IS NOT NULL AND active=1").fetchone()[0]
    con.close()
    return n


def add_user(email: str, name: str, role: str, password: str) -> dict:
    """An account created by the admin for someone else."""
    if role not in SIGNUP_ROLES:
        raise AuthError("Ledger has a single admin account. New accounts are employees or auditors.")
    return create_user(email, name, role, password)


def setup_first_admin(email: str, name: str, password: str) -> dict:
    """One-time setup: allowed only while Ledger has no admin."""
    if has_admin():
        raise AuthError("Ledger already has its admin account. Sign in instead.")
    return create_user(email, name, "admin", password)


def seed_auditor_from_env() -> None:
    """Create the ready-made auditor named in AUDITOR_EMAIL / AUDITOR_PASSWORD if that email is free."""
    email, password = os.environ.get("AUDITOR_EMAIL", "").strip(), os.environ.get("AUDITOR_PASSWORD", "")
    if not email or not password:
        return
    con = _db()
    exists = con.execute("SELECT 1 FROM users WHERE email=?", (email.lower(),)).fetchone()
    con.close()
    if exists:
        return
    try:
        create_user(email, os.environ.get("AUDITOR_NAME", "").strip() or "Auditor", "auditor", password)
        log.info("Created the auditor account %s from the environment.", email.lower())
    except AuthError as e:
        log.error("AUDITOR_EMAIL / AUDITOR_PASSWORD could not be used: %s", e)


# The admin every fresh install starts with, so anyone who clones the project can sign in at once.
# These are published in the README: a real deployment must set ADMIN_EMAIL / ADMIN_PASSWORD instead.
DEFAULT_ADMIN = {"email": "admin@fiscalai.local", "password": "FiscalAI-Admin-2026", "name": "FiscalAI Admin"}


def configured_admin() -> dict | None:
    """The admin this installation is meant to have: ADMIN_EMAIL / ADMIN_PASSWORD, otherwise the built-in one."""
    email, password = os.environ.get("ADMIN_EMAIL", "").strip().lower(), os.environ.get("ADMIN_PASSWORD", "")
    name = os.environ.get("ADMIN_NAME", "").strip()
    if email and password:
        return {"email": email, "password": password, "name": name or "Administrator", "builtin": False}
    if os.environ.get("DEFAULT_ADMIN", "on").strip().lower() in {"off", "0", "false", "no"}:
        return None
    return {**DEFAULT_ADMIN, "name": name or DEFAULT_ADMIN["name"], "builtin": True}


def seed_admin_from_env() -> None:
    """Make sure, on every start, that the configured admin exists and can sign in.

    The configuration is the source of truth: the single admin account is created if it is missing and
    repaired if its email, password, role or active flag differ (an old database, a forgotten password,
    a changed setting). So the admin sign-in shown in the README, or set on the host, always works after
    a restart, and nobody ever has to register an admin. With DEFAULT_ADMIN=off and no ADMIN_EMAIL /
    ADMIN_PASSWORD nothing is touched and the one-time setup form is used instead.
    """
    want = configured_admin()
    if not want:
        return
    try:
        _clean(want["email"], want["name"], "admin", want["password"])
    except AuthError as e:
        log.error("The admin settings could not be used: %s", e)
        return
    con = _db()
    try:
        current = con.execute("SELECT * FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
        same_email = con.execute("SELECT * FROM users WHERE email=?", (want["email"],)).fetchone()
        target = same_email or current                      # reuse the account with that address, else the admin
        if target is None:
            with con:
                con.execute(
                    "INSERT INTO users (email, name, role, password_hash, active, created_at) VALUES (?,?,?,?,1,?)",
                    (want["email"], want["name"], "admin", hash_password(want["password"]), _iso(_now())))
            log.info("Created the admin account %s.", want["email"])
        else:
            with con:
                # There is one admin: if another account holds the role, it steps down to auditor.
                con.execute("UPDATE users SET role='auditor' WHERE role='admin' AND id<>?", (target["id"],))
                if not verify_password(want["password"], target["password_hash"]):
                    con.execute("UPDATE users SET password_hash=? WHERE id=?",
                                (hash_password(want["password"]), target["id"]))
                    con.execute("DELETE FROM sessions WHERE user_id=?", (target["id"],))
                    log.info("Reset the admin password of %s from the configuration.", want["email"])
                con.execute("UPDATE users SET email=?, role='admin', active=1, requested_role=NULL WHERE id=?",
                            (want["email"], target["id"]))
        if want["builtin"]:
            log.warning("The admin is the built-in %s with the published default password. "
                        "Set ADMIN_EMAIL and ADMIN_PASSWORD before putting this on the internet.", want["email"])
    finally:
        con.close()


def list_users() -> list[dict]:
    con = _db()
    rows = [public(r) for r in con.execute(
        "SELECT * FROM users ORDER BY active DESC, requested_role IS NULL, role, name").fetchall()]
    con.close()
    return rows


def get_user(uid: int) -> dict | None:
    con = _db()
    r = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    con.close()
    return public(r) if r else None


def update_user(uid: int, *, name: str | None = None, role: str | None = None, active: bool | None = None,
                password: str | None = None, decline_request: bool = False) -> dict | None:
    """Change an account. The single admin keeps its role and stays active; nobody else becomes admin."""
    con = _db()
    try:
        r = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not r:
            return None
        _, name = _clean(r["email"], name, role, password)
        if r["role"] == "admin" and ((role is not None and role != "admin") or active is False):
            raise AuthError("The admin account can't be demoted or deactivated.")
        if r["role"] != "admin" and role == "admin":
            raise AuthError("Ledger has a single admin account. Nobody else can be made admin.")
        sets, args = [], []
        for col, val in (("name", name), ("role", role),
                         ("active", None if active is None else int(active)),
                         ("password_hash", hash_password(password) if password is not None else None)):
            if val is not None:
                sets.append(f"{col}=?")
                args.append(val)
        with con:
            if sets:
                con.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*args, uid))
            # Setting a role answers a pending request (approving it, or settling it as employee).
            if role is not None or decline_request:
                con.execute("UPDATE users SET requested_role=NULL WHERE id=?", (uid,))
            # A new password or a deactivation ends that person's open sessions. A role change does not
            # need to: the role is read from the database on every request, so it applies at once.
            if password is not None or active is False:
                con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        return public(con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
    finally:
        con.close()


def change_own_password(uid: int, current: str, new: str, keep_token: str | None = None) -> None:
    check_password(new)
    con = _db()
    try:
        r = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not r or not verify_password(current or "", r["password_hash"]):
            raise AuthError("The current password isn't right.")
        with con:
            con.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new), uid))
            # Sign out every other device; keep the session that made the change.
            con.execute("DELETE FROM sessions WHERE user_id=? AND token_sha<>?",
                        (uid, _sha(keep_token) if keep_token else ""))
    finally:
        con.close()


# ------------------------------------------------------------------ sign-in and sessions
def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


_dummy: list[str] = []


def _dummy_hash() -> str:
    if not _dummy:
        _dummy.append(hash_password(secrets.token_hex(8)))
    return _dummy[0]


def authenticate(email: str, password: str) -> dict:
    """Return the account, or raise AuthError. Wrong email and wrong password look the same."""
    email = (email or "").strip().lower()
    fails, locked_until = _fails.get(email, (0, 0.0))
    if locked_until > time.monotonic():
        raise AuthError("Too many wrong passwords. Wait a minute and try again.")
    con = _db()
    r = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    # Hash even when the account is unknown, so response time does not reveal which emails exist.
    ok = verify_password(password or "", r["password_hash"] if r else _dummy_hash())
    if not (r and ok and r["active"]):
        con.close()
        fails += 1
        _fails[email] = (0, time.monotonic() + LOCK_SECONDS) if fails >= MAX_FAILS else (fails, 0.0)
        raise AuthError("That email and password don't match an active account.")
    _fails.pop(email, None)
    with con:
        con.execute("UPDATE users SET last_login=? WHERE id=?", (_iso(_now()), r["id"]))
    row = con.execute("SELECT * FROM users WHERE id=?", (r["id"],)).fetchone()
    con.close()
    return public(row)


def start_session(uid: int) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    con = _db()
    with con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (_iso(now),))
        con.execute("INSERT INTO sessions (token_sha, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                    (_sha(token), uid, _iso(now), _iso(now + timedelta(hours=SESSION_HOURS))))
    con.close()
    return token


def user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    con = _db()
    r = con.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.token_sha=? AND s.expires_at > ? AND u.active=1", (_sha(token), _iso(_now()))).fetchone()
    con.close()
    return public(r) if r else None


def end_session(token: str | None) -> None:
    if not token:
        return
    con = _db()
    with con:
        con.execute("DELETE FROM sessions WHERE token_sha=?", (_sha(token),))
    con.close()
