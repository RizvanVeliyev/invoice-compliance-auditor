import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()
logging.basicConfig(level=logging.INFO)

import assistant  # noqa: E402  (after load_dotenv so env vars are visible)
import auth  # noqa: E402
import service  # noqa: E402
import submissions  # noqa: E402

BASE_DIR = Path(__file__).parent
POLICY = json.loads((BASE_DIR / "policy.json").read_text(encoding="utf-8"))
SAMPLES_DIR = BASE_DIR / "sample_invoices"
SAMPLE_PDFS_DIR = BASE_DIR / "sample_pdfs"



@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        auth.seed_admin_from_env()
        auth.seed_auditor_from_env()
    except Exception:  # noqa: BLE001 - a bad seed must not stop the API; the setup screen still works
        logging.getLogger("ledger.auth").exception("Could not seed the accounts from the environment")
    yield


app = FastAPI(title="Ledger — Invoice Compliance Auditor API", lifespan=lifespan)

origins = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PATCH"],
                   allow_headers=["*"])


# ------------------------------------------------------------------ who is calling
def current_user(request: Request) -> dict:
    user = auth.user_for_token(request.cookies.get(auth.SESSION_COOKIE))
    if not user:
        raise HTTPException(401, "Sign in to continue.")
    return user


def require_role(*roles: str):
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "Your account doesn't have access to this.")
        return user
    return dep


require_auditor = require_role(*auth.AUDIT_ROLES)
require_admin = require_role("admin")


def _set_session(response: Response, user: dict) -> None:
    # HttpOnly: page scripts cannot read it. SameSite=Lax: other sites cannot send it with a POST.
    response.set_cookie(
        auth.SESSION_COOKIE, auth.start_session(user["id"]), max_age=auth.SESSION_HOURS * 3600,
        httponly=True, samesite="lax", path="/",
        secure=os.environ.get("COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"})


async def _read_upload(file: UploadFile) -> bytes:
    # Read at most limit+1 bytes so an oversized upload is rejected without loading it all.
    data = await file.read(service.MAX_FILE_BYTES + 1)
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > service.MAX_FILE_BYTES:
        raise HTTPException(413, "The file is larger than 5 MB.")
    return data


class AnalyzeRequest(BaseModel):
    invoice_text: str


@app.get("/api/health")
def health():
    return {"status": "ok", "provider": os.environ.get("LLM_PROVIDER", "offline"),
            "auditor_signup": "approval" if auth.auditor_signup_needs_approval() else "open"}


@app.get("/api/policy")
def get_policy():
    return POLICY


# ------------------------------------------------------------------ sign-in
class Credentials(BaseModel):
    email: str
    password: str


class Setup(Credentials):
    name: str


class Registration(Credentials):
    name: str
    role: str = "employee"


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@app.get("/api/auth/state")
def auth_state(request: Request):
    """What the UI needs on load: is anyone signed in, and does Ledger still need its admin?"""
    return {"user": auth.user_for_token(request.cookies.get(auth.SESSION_COOKIE)),
            "setup_required": not auth.has_admin()}


@app.post("/api/auth/register")
def auth_register(body: Registration, response: Response):
    """Open sign-up: the person says whether they are an employee or an auditor."""
    try:
        user = auth.register(body.email, body.name, body.role, body.password)
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    _set_session(response, user)
    return user


@app.post("/api/auth/setup")
def auth_setup(body: Setup, response: Response):
    try:
        user = auth.setup_first_admin(body.email, body.name, body.password)
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    _set_session(response, user)
    return user


@app.post("/api/auth/login")
def auth_login(body: Credentials, response: Response):
    try:
        user = auth.authenticate(body.email, body.password)
    except auth.AuthError as e:
        raise HTTPException(401, str(e))
    _set_session(response, user)
    return user


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    auth.end_session(request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"ok": True}


@app.post("/api/auth/password")
def auth_password(body: PasswordChange, request: Request, user: dict = Depends(current_user)):
    try:
        auth.change_own_password(user["id"], body.current_password, body.new_password,
                                 keep_token=request.cookies.get(auth.SESSION_COOKIE))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ------------------------------------------------------------------ accounts (admin)
class NewUser(BaseModel):
    email: str
    name: str
    role: str
    password: str


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = None
    decline_request: bool = False        # refuse a pending request for auditor access


@app.get("/api/users")
def users_list(_: dict = Depends(require_admin)):
    return auth.list_users()


@app.get("/api/users/pending")
def users_pending(_: dict = Depends(require_admin)):
    """How many people are waiting for the admin to approve auditor access (shown in the top bar)."""
    return {"pending": auth.pending_requests()}


@app.post("/api/users")
def users_create(body: NewUser, _: dict = Depends(require_admin)):
    try:
        return auth.add_user(body.email, body.name, body.role, body.password)
    except auth.AuthError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/users/{uid}")
def users_update(uid: int, body: UserPatch, _: dict = Depends(require_admin)):
    try:
        user = auth.update_user(uid, name=body.name, role=body.role, active=body.active, password=body.password,
                                decline_request=body.decline_request)
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    if not user:
        raise HTTPException(404, "Account not found.")
    return user


# ------------------------------------------------------------------ quick check
@app.get("/api/samples")
def get_samples():
    samples = []
    if SAMPLES_DIR.exists():
        for path in sorted(SAMPLES_DIR.glob("*.txt")):
            samples.append({
                "id": path.stem,
                "label": path.stem.split("-", 1)[-1].replace("-", " ").title(),
                "text": path.read_text(encoding="utf-8"),
            })
    return samples


def _run(**kw):
    try:
        return service.analyze(POLICY, **kw)
    except KeyError as e:
        raise HTTPException(500, f"Missing API key in environment: {e}. Set it in backend/.env "
                                 f"or run with LLM_PROVIDER=offline for template-format invoices.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001 - surface real error to the demo UI
        raise HTTPException(500, f"Analysis failed: {e}")


@app.post("/api/analyze", dependencies=[Depends(current_user)])
def analyze(req: AnalyzeRequest):
    if not req.invoice_text.strip():
        raise HTTPException(400, "invoice_text is empty")
    if len(req.invoice_text) > service.MAX_TEXT_CHARS:
        raise HTTPException(413, f"invoice_text exceeds {service.MAX_TEXT_CHARS} characters")
    return _run(text=req.invoice_text)


@app.post("/api/analyze-file", dependencies=[Depends(current_user)])
async def analyze_file(file: UploadFile = File(...)):
    data = await _read_upload(file)
    mime = file.content_type or ""
    if mime.startswith("text/") or (file.filename or "").endswith(".txt"):
        return _run(text=data.decode("utf-8", errors="replace")[: service.MAX_TEXT_CHARS])
    return _run(file_bytes=data, mime=mime)


@app.get("/api/audit-log", dependencies=[Depends(require_auditor)])
def audit_log(limit: int = 25):
    return service.read_audit(max(1, min(limit, 200)))


# ------------------------------------------------------------------ employee submissions
@app.get("/api/sample-pdfs")
def sample_pdfs():
    if not SAMPLE_PDFS_DIR.exists():
        return []
    return [{"name": p.name, "label": p.stem.split("-", 1)[-1].replace("-", " ").capitalize()}
            for p in sorted(SAMPLE_PDFS_DIR.glob("*.pdf"))]


@app.get("/api/sample-pdfs/{name}")
def sample_pdf(name: str):
    p = (SAMPLE_PDFS_DIR / name).resolve()
    if p.parent != SAMPLE_PDFS_DIR.resolve() or p.suffix != ".pdf" or not p.exists():
        raise HTTPException(404, "No such sample.")
    return FileResponse(p, media_type="application/pdf", filename=p.name)


@app.post("/api/submissions")
async def submit_invoice(file: UploadFile = File(...), note: str = Form(""), currency: str = Form(""),
                         user: dict = Depends(current_user)):
    data = await _read_upload(file)
    try:
        return submissions.create(POLICY, data, file.content_type or "", file.filename or "", user, note, currency)
    except submissions.DuplicateInvoice as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/my/submissions")
def my_submissions(user: dict = Depends(current_user)):
    return submissions.list_mine(user["id"], limit=500)


class ChatMessage(BaseModel):
    message: str
    lang: str = "en"


@app.post("/api/chat")
def chat(body: ChatMessage, user: dict = Depends(current_user)):
    """The assistant: policy questions, "what if" checks and the person's own invoices. Read-only."""
    if not body.message.strip():
        raise HTTPException(400, "Write a question first.")
    return assistant.reply(POLICY, user, body.message, body.lang)


@app.get("/api/my/report")
def my_report(months: int = 6, user: dict = Depends(current_user)):
    """The signed-in person's own spending: by month, category and vendor."""
    return submissions.report(POLICY, user["id"], months)


# ------------------------------------------------------------------ auditor desk
class Decision(BaseModel):
    decision: str
    comment: str = ""


class Reason(BaseModel):
    text: str


@app.get("/api/alerts/summary", dependencies=[Depends(require_auditor)])
def alerts_summary():
    return submissions.alert_summary()


@app.get("/api/overview", dependencies=[Depends(require_auditor)])
def overview(days: int = 14):
    return submissions.overview(POLICY, max(7, min(days, 60)))


@app.get("/api/export.csv", dependencies=[Depends(require_auditor)])
def export_csv():
    return Response(submissions.export_csv(POLICY), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="ledger-invoices.csv"'})


@app.get("/api/employees", dependencies=[Depends(require_auditor)])
def employees():
    """Everyone with an account and what they have submitted."""
    return submissions.people(POLICY, auth.list_users())


@app.get("/api/employees/{uid}", dependencies=[Depends(require_auditor)])
def employee(uid: int, months: int = 6):
    """One person's spending report and their invoices, for the audit team."""
    user = auth.get_user(uid)
    if not user:
        raise HTTPException(404, "Account not found.")
    return {"user": user, "report": submissions.report(POLICY, uid, months),
            "submissions": submissions.list_(user_id=uid, limit=500)}


@app.get("/api/submissions", dependencies=[Depends(require_auditor)])
def list_submissions(response: Response, status: str | None = None, state: str | None = None, limit: int = 100,
                     q: str | None = None, user_id: int | None = None, currency: str | None = None,
                     date_from: str | None = None, date_to: str | None = None,
                     page: int | None = None, page_size: int = 20):
    """Filter and page through submissions. The total number of matches comes back in X-Total-Count."""
    if page is not None:
        limit = max(1, min(page_size, 100))
    offset = (max(1, page) - 1) * limit if page is not None else 0
    rows, total = submissions.list_page(status, state, limit, q, user_id, currency, date_from, date_to, offset)
    response.headers["X-Total-Count"] = str(total)
    return rows


@app.get("/api/submissions/{sid}", dependencies=[Depends(require_auditor)])
def get_submission(sid: int):
    s = submissions.get(sid)
    if not s:
        raise HTTPException(404, "Submission not found.")
    submissions.mark_seen(sid)
    return s


@app.get("/api/submissions/{sid}/file")
def get_submission_file(sid: int, user: dict = Depends(current_user)):
    f = submissions.file_path(sid)
    # An employee can open only their own invoices; say "not found" rather than reveal that one exists.
    if not f or (user["role"] not in auth.AUDIT_ROLES and f[3] != user["id"]):
        raise HTTPException(404, "File not found.")
    path, mime, name, _ = f
    return FileResponse(path, media_type=mime, headers={
        "Content-Disposition": f'inline; filename="{name.replace(chr(34), "")}"',
        "X-Content-Type-Options": "nosniff"})


@app.post("/api/submissions/{sid}/decision")
def decide(sid: int, body: Decision, reviewer: dict = Depends(require_auditor)):
    try:
        s = submissions.decide(sid, body.decision, body.comment, reviewer)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not s:
        raise HTTPException(404, "Submission not found.")
    return s


@app.post("/api/submissions/{sid}/reopen")
def reopen(sid: int, body: Reason, reviewer: dict = Depends(require_auditor)):
    try:
        s = submissions.reopen(sid, body.text, reviewer)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not s:
        raise HTTPException(404, "Submission not found.")
    return s


@app.post("/api/submissions/{sid}/notes")
def add_note(sid: int, body: Reason, author: dict = Depends(require_auditor)):
    try:
        s = submissions.add_note(sid, body.text, author)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not s:
        raise HTTPException(404, "Submission not found.")
    return s
