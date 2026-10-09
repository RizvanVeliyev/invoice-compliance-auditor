"""Shared fixtures: an isolated database with one account per role, and a sign-in helper."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import auth
import main
import service

PDFS = Path(__file__).parent.parent / "sample_pdfs"
PASSWORD = "correct-horse-9"
PEOPLE = {
    "admin": ("admin@nordvik.test", "Farid Admin"),
    "auditor": ("auditor@nordvik.test", "Gunel Auditor"),
    "employee": ("murad@nordvik.test", "Murad Quliyev"),
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "audit.db")
    monkeypatch.setattr(auth, "SCRYPT_N", 2 ** 8)          # cheap hashes: these tests sign in many times
    monkeypatch.setattr(auth, "_fails", {})
    monkeypatch.setattr(auth, "_dummy", [])
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("AUDITOR_SIGNUP", raising=False)
    for role, (email, name) in PEOPLE.items():
        auth.create_user(email, name, role, PASSWORD)
    return TestClient(main.app)


@pytest.fixture
def as_(client):
    """as_("auditor") signs the shared client in as that role (or as any email)."""
    def sign_in(who: str, password: str = PASSWORD):
        email = PEOPLE[who][0] if who in PEOPLE else who
        client.cookies.clear()
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()
    return sign_in


@pytest.fixture
def submit(client):
    def send(name, data=None, mime="application/pdf", **form):
        data = data if data is not None else (PDFS / name).read_bytes()
        return client.post("/api/submissions", files={"file": (name, data, mime)},
                           data={"note": "Baku trip", **form})
    return send
