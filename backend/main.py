import hmac
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()
logging.basicConfig(level=logging.INFO)

import service  # noqa: E402  (after load_dotenv so env vars are visible)
import submissions  # noqa: E402

BASE_DIR = Path(__file__).parent
POLICY = json.loads((BASE_DIR / "policy.json").read_text(encoding="utf-8"))
SAMPLES_DIR = BASE_DIR / "sample_invoices"
SAMPLE_PDFS_DIR = BASE_DIR / "sample_pdfs"

app = FastAPI(title="Ledger — Invoice Compliance Auditor API")

origins = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])


def require_auditor(x_auditor_pin: str | None = Header(default=None), pin: str | None = Query(default=None)):
    """Auditor-only endpoints. Open when AUDITOR_PIN is unset (local demo); otherwise the
    PIN must arrive as the X-Auditor-Pin header (or ?pin= for the PDF preview iframe)."""
    expected = os.environ.get("AUDITOR_PIN", "").strip()
    if not expected:
        return
    given = (x_auditor_pin or pin or "").strip()
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(401, "Auditor PIN required.")


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
            "auditor_pin_required": bool(os.environ.get("AUDITOR_PIN", "").strip())}


@app.get("/api/policy")
def get_policy():
    return POLICY


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


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    if not req.invoice_text.strip():
        raise HTTPException(400, "invoice_text is empty")
    if len(req.invoice_text) > service.MAX_TEXT_CHARS:
        raise HTTPException(413, f"invoice_text exceeds {service.MAX_TEXT_CHARS} characters")
    return _run(text=req.invoice_text)


@app.post("/api/analyze-file")
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
async def submit_invoice(file: UploadFile = File(...), employee_name: str = Form(...),
                         employee_email: str = Form(""), note: str = Form("")):
    data = await _read_upload(file)
    try:
        return submissions.create(POLICY, data, file.content_type or "", file.filename or "",
                                  employee_name, employee_email, note)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ auditor desk
class Decision(BaseModel):
    decision: str
    comment: str = ""
    reviewer: str = ""


@app.get("/api/alerts/summary", dependencies=[Depends(require_auditor)])
def alerts_summary():
    return submissions.alert_summary()


@app.get("/api/submissions", dependencies=[Depends(require_auditor)])
def list_submissions(status: str | None = None, state: str | None = None, limit: int = 100):
    return submissions.list_(status, state, limit)


@app.get("/api/submissions/{sid}", dependencies=[Depends(require_auditor)])
def get_submission(sid: int):
    s = submissions.get(sid)
    if not s:
        raise HTTPException(404, "Submission not found.")
    submissions.mark_seen(sid)
    return s


@app.get("/api/submissions/{sid}/file", dependencies=[Depends(require_auditor)])
def get_submission_file(sid: int):
    f = submissions.file_path(sid)
    if not f:
        raise HTTPException(404, "File not found.")
    path, mime, name = f
    return FileResponse(path, media_type=mime, headers={
        "Content-Disposition": f'inline; filename="{name.replace(chr(34), "")}"',
        "X-Content-Type-Options": "nosniff"})


@app.post("/api/submissions/{sid}/decision", dependencies=[Depends(require_auditor)])
def decide(sid: int, body: Decision):
    try:
        s = submissions.decide(sid, body.decision, body.comment, body.reviewer)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not s:
        raise HTTPException(404, "Submission not found.")
    return s
