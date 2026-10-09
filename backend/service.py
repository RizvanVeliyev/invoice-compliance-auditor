"""Pipeline: extract (LLM) -> evaluate (rules) -> audit-log."""

import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import llm_providers
import rules_engine

DB_PATH = Path(os.environ.get("AUDIT_DB_PATH", Path(__file__).parent / "data" / "audit.db"))
MAX_TEXT_CHARS = 20_000
MAX_FILE_BYTES = 5 * 1024 * 1024
IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
HISTORY_WINDOW = 500          # how many past checks to compare against
log = logging.getLogger("ledger.audit")


def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, provider TEXT,"
        " input_sha256 TEXT, input_excerpt TEXT, policy_version TEXT, status TEXT, result_json TEXT)"
    )
    return con


def log_audit(provider, raw: bytes, excerpt: str, policy, result) -> bool:
    """Write one audit row. Never breaks the analysis, but a failure is logged
    and reported back (meta.audit_logged = False) instead of being hidden."""
    try:
        con = _db()
        with con:
            con.execute(
                "INSERT INTO audit (ts, provider, input_sha256, input_excerpt, policy_version, status, result_json)"
                " VALUES (?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), provider,
                 hashlib.sha256(raw).hexdigest(), excerpt[:200], policy["policy_version"],
                 result["status"], json.dumps(result)),
            )
        con.close()
        return True
    except Exception:  # noqa: BLE001 - an audit write failure must not lose the verdict
        log.exception("Audit log write failed (db=%s)", DB_PATH)
        return False


def read_audit(limit: int = 25):
    con = _db()
    rows = con.execute(
        "SELECT id, ts, provider, input_sha256, input_excerpt, policy_version, status FROM audit"
        " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    keys = ["id", "ts", "provider", "input_sha256", "input_excerpt", "policy_version", "status"]
    return [dict(zip(keys, r)) for r in rows]


def _key(s) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", str(s or "").lower())).strip()


def history_warnings(policy: dict, result: dict, input_sha: str) -> list[str]:
    """Compare a new result with earlier checks: possible duplicates and split purchases.

    Warnings only. They never change status: the verdict stays a pure function
    of policy + invoice. Re-checking the SAME input (same SHA-256) is not a duplicate.
    """
    vendor, emp, amt = _key(result.get("vendor")), _key(result.get("employee")), result.get("amount")
    date, cur = (result.get("date") or "").strip(), result.get("currency") or ""
    if not vendor or not isinstance(amt, (int, float)) or amt <= 0:
        return []
    try:
        con = _db()
        rows = con.execute("SELECT id, input_sha256, result_json FROM audit ORDER BY id DESC LIMIT ?",
                           (HISTORY_WINDOW,)).fetchall()
        con.close()
    except Exception:  # noqa: BLE001
        return []

    tiers = [t for t in policy["approval_thresholds"] if t.get("required_approval")]
    warnings, seen_sha = [], {input_sha}
    for rid, sha, rj in rows:
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        try:
            old = json.loads(rj)
        except ValueError:
            continue
        o_amt = old.get("amount")
        if _key(old.get("vendor")) != vendor or not isinstance(o_amt, (int, float)) or o_amt <= 0:
            continue
        if (old.get("currency") or "") != cur:
            continue
        same_emp = _key(old.get("employee")) == emp and emp
        same_date = date and (old.get("date") or "").strip() == date
        if same_date and abs(o_amt - amt) < 0.005:
            warnings.append(f"Possible duplicate: check #{rid} has the same vendor, amount ({o_amt:g} {cur}) "
                            f"and date ({date}).")
        elif same_date and same_emp:
            total = o_amt + amt
            for t in tiers:
                lo = t["min"]
                below = (lambda x: x < lo) if t["min_inclusive"] else (lambda x: x <= lo)
                if below(o_amt) and below(amt) and not below(total):
                    warnings.append(
                        f"Possible split purchase: check #{rid} ({o_amt:g} {cur}) + this invoice ({amt:g} {cur}) "
                        f"from the same vendor, employee and date total {total:g} {cur}, which would need "
                        f"{t['label']} approval as one purchase.")
                    break
    return warnings[:5]


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages).strip()


def analyze(policy: dict, text: str | None = None, file_bytes: bytes | None = None,
            mime: str | None = None, provider: str | None = None) -> dict:
    t0 = time.perf_counter()
    raw = (text or "").encode() if text is not None else (file_bytes or b"")
    excerpt = text or f"[file {mime}, {len(file_bytes or b'')} bytes]"
    source = "text"

    if text is None and file_bytes is not None:
        if mime == "application/pdf":
            extracted = pdf_text(file_bytes)
            if len(extracted) >= 40:        # real text layer: cheapest, most exact
                text, file_bytes, mime, source = extracted, None, None, "pdf-text-layer"
            else:                            # scanned PDF: send to a vision-capable model
                source = "pdf-scanned"
        elif mime in IMAGE_MIMES:
            source = "image"
        else:
            raise ValueError(f"Unsupported file type: {mime}")

    record, usage, prov = llm_providers.extract_invoice(text, file_bytes, mime, provider)
    result = rules_engine.evaluate(policy, record)
    result["extracted"] = record
    result["meta"] = {
        "provider": prov,
        "source": source,
        "policy_version": policy["policy_version"],
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "estimated_cost_usd": llm_providers.estimate_cost(usage),
        "decided_by": "deterministic rules engine (LLM used for extraction only)",
    }
    sha = hashlib.sha256(raw).hexdigest()
    result["history_warnings"] = history_warnings(policy, result, sha)
    result["meta"]["audit_logged"] = log_audit(prov, raw, excerpt, policy, result)
    return result
