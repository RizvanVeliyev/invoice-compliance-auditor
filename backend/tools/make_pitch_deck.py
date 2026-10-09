"""
Build the pitch deck as a 16:9 PDF.

  pip install reportlab
  python tools/make_pitch_deck.py            # writes ../FiscalAI-pitch-deck.pdf

The live-model numbers on the testing slide are read from quality_test_results.json
when that file comes from a live run; otherwise the slide says they are not measured.
"""
import json
import statistics
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT.parent / "FiscalAI-pitch-deck.pdf"
W, H = 960, 540
PAPER, SHEET, INK, INK2, INK3 = HexColor("#eef2e6"), HexColor("#fbfcf7"), HexColor("#18261f"), HexColor("#44554b"), HexColor("#6b7a70")
BLUE, DEEP, OK, BAD, WARN, RULE = HexColor("#2b4c9b"), HexColor("#1f3a7a"), HexColor("#1e6b45"), HexColor("#b3261e"), HexColor("#c77b2a"), HexColor("#c9d8c2")
M = 56  # page margin
MODEL, PRICE_IN, PRICE_OUT = "gemini-3.8-flash", 0.75, 3.75      # USD per million tokens (Google's price page)


def live_results():
    """Numbers from a live run of run_quality_tests.py, or None when the last run was offline."""
    try:
        rows = json.loads((ROOT / "quality_test_results.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ran = [r for r in rows if not r.get("skipped")]
    tin = sum(r.get("usage", {}).get("input_tokens", 0) for r in ran)
    tout = sum(r.get("usage", {}).get("output_tokens", 0) for r in ran)
    if not ran or tin == 0:
        return None
    ms = [r["ms"] for r in ran if "ms" in r]
    cost = (tin * PRICE_IN + tout * PRICE_OUT) / 1_000_000 / len(ran)
    return {"passed": sum(1 for r in ran if r.get("ok")), "ran": len(ran), "median_s": statistics.median(ms) / 1000,
            "cost": cost, "failed": [r["id"] for r in ran if not r.get("ok")]}


class Deck:
    def __init__(self):
        self.c = canvas.Canvas(str(OUT), pagesize=(W, H))
        self.c.setTitle("FiscalAI — pitch deck")
        self.c.setAuthor("FiscalAI")
        self.n = 0

    def mark(self, x, y, s=1.0, paper=BLUE):
        """The receipt logo: torn lower edge, two lines, a check."""
        c = self.c
        c.saveState()
        c.translate(x, y)
        c.scale(s, -s)
        p = c.beginPath()
        p.moveTo(7, 3.5); p.lineTo(25, 3.5); p.lineTo(27, 5.5); p.lineTo(27, 28)
        for px, py in ((23.33, 25.8), (19.67, 28), (16, 25.8), (12.33, 28), (8.67, 25.8), (5, 28)):
            p.lineTo(px, py)
        p.lineTo(5, 5.5); p.close()
        c.setFillColor(paper); c.drawPath(p, fill=1, stroke=0)
        c.setStrokeColor(white); c.setLineCap(1); c.setLineJoin(1)
        c.setLineWidth(1.8); c.line(10, 9.5, 22, 9.5); c.line(10, 13.5, 17, 13.5)
        c.setLineWidth(2.6)
        q = c.beginPath(); q.moveTo(11, 19); q.lineTo(14.2, 22.2); q.lineTo(21.5, 15); c.drawPath(q, fill=0, stroke=1)
        c.restoreState()

    def page(self, title, kicker=""):
        c = self.c
        if self.n:
            c.showPage()
        self.n += 1
        c.setFillColor(PAPER); c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setStrokeColor(RULE); c.setLineWidth(0.6)
        for y in range(28, H, 28):                       # ledger ruling
            c.line(0, y, W, y)
        c.setStrokeColor(HexColor("#e2b7b3")); c.line(30, 0, 30, H); c.line(33, 0, 33, H)
        self.mark(M, H - 30, 0.8)
        c.setFillColor(INK); c.setFont("Helvetica-Bold", 13); c.drawString(M + 30, H - 49, "Fiscal")
        c.setFillColor(BLUE); c.drawString(M + 30 + c.stringWidth("Fiscal", "Helvetica-Bold", 13), H - 49, "AI")
        c.setFillColor(INK3); c.setFont("Helvetica", 9); c.drawRightString(W - M, H - 48, f"{self.n}")
        if kicker:
            c.setFillColor(BLUE); c.setFont("Helvetica-Bold", 10); c.drawString(M, H - 92, kicker.upper())
        c.setFillColor(INK); c.setFont("Helvetica-Bold", 28); c.drawString(M, H - 124, title)
        return H - 160

    def card(self, x, y, w, h, accent=None):
        c = self.c
        c.setFillColor(SHEET); c.setStrokeColor(HexColor("#d6e0d0")); c.setLineWidth(0.8)
        c.roundRect(x, y - h, w, h, 8, fill=1, stroke=1)
        if accent:
            c.setFillColor(accent); c.roundRect(x, y - 5, w, 5, 2, fill=1, stroke=0)

    def text(self, x, y, s, size=13, color=INK2, bold=False, width=None, lead=None):
        """Draw a paragraph with simple word wrapping. Returns the y below it."""
        c, font = self.c, "Helvetica-Bold" if bold else "Helvetica"
        lead = lead or size * 1.42
        c.setFillColor(color); c.setFont(font, size)
        for para in s.split("\n"):
            line = ""
            for word in para.split(" "):
                trial = (line + " " + word).strip()
                if width and c.stringWidth(trial, font, size) > width and line:
                    c.drawString(x, y, line); y -= lead; line = word
                else:
                    line = trial
            c.drawString(x, y, line); y -= lead
        return y

    def bullets(self, x, y, items, size=13, width=None, gap=6, color=INK2):
        for it in items:
            self.c.setFillColor(BLUE); self.c.circle(x + 3, y + size * 0.32, 2.6, fill=1, stroke=0)
            y = self.text(x + 16, y, it, size, color, width=(width - 16) if width else None) - gap
        return y

    def stat(self, x, y, w, big, label, color=INK, sub=""):
        self.card(x, y, w, 118, color)
        self.c.setFillColor(color); self.c.setFont("Courier-Bold", 38); self.c.drawString(x + 16, y - 56, big)
        yy = self.text(x + 16, y - 78, label, 11.5, INK, bold=True, width=w - 30)
        if sub:
            self.text(x + 16, yy + 2, sub, 10, INK3, width=w - 30)

    def save(self):
        self.c.save()


def build():
    d, live = Deck(), live_results()
    c = d.c
    col = (W - 2 * M - 28) / 2

    # 1 ---------------------------------------------------------------- title
    d.n += 1
    c.setFillColor(DEEP); c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(BLUE); c.rect(0, 0, W, 150, fill=1, stroke=0)
    c.setFillColor(white); c.roundRect(M, H - 190, 96, 96, 18, fill=1, stroke=0)
    d.mark(M + 12, H - 100, 2.25)
    c.setFillColor(white); c.setFont("Helvetica-Bold", 60); c.drawString(M, H - 270, "FiscalAI")
    c.setFont("Helvetica", 22); c.drawString(M, H - 308, "Every invoice checked against the expense policy")
    c.drawString(M, H - 336, "before anyone pays it.")
    c.setFont("Helvetica-Bold", 14); c.drawString(M, 86, "The AI reads. The code decides.")
    c.setFont("Helvetica", 12); c.drawString(M, 62, "Track: AI Enterprise Solutions   |   github.com/RizvanVeliyev/invoice-compliance-auditor")

    # 2 ---------------------------------------------------------------- problem
    y = d.page("Checking expenses by hand is slow and misses things", "The user and the problem")
    d.card(M, y, col, 300, BLUE)
    d.text(M + 18, y - 32, "Who", 12, BLUE, bold=True)
    yy = d.text(M + 18, y - 54, "The finance / audit team of a mid-size company, and every employee who files an expense.", 13.5, INK, width=col - 36)
    d.text(M + 18, yy - 10, "Today", 12, BLUE, bold=True)
    d.bullets(M + 18, yy - 32, ["Spreadsheets and manual review against a policy PDF",
                                "Per-night and per-person division done in the head",
                                "Dollars and euros converted by hand",
                                "The employee hears nothing until paid or bounced"], 12.5, col - 36)
    x2 = M + col + 28
    d.card(x2, y, col, 300, BAD)
    d.text(x2 + 18, y - 32, "What slips through", 12, BAD, bold=True)
    d.bullets(x2 + 18, y - 56, ["A 380-a-night hotel hidden inside a 3-night total",
                                "A $650 purchase that is really 1,105 AZN and needs two approvals",
                                "A missing approval, an unlisted vendor",
                                "The same invoice submitted twice",
                                "A note in the invoice telling the AI to approve it"], 12.5, col - 36)

    # 3 ---------------------------------------------------------------- outcome
    y = d.page("A verdict in seconds, with the rule and the maths", "The outcome")
    w3 = (W - 2 * M - 2 * 20) / 3
    for i, (head, color, items) in enumerate([
        ("Employee", BLUE, ["Uploads a PDF or a photo", "Stamped answer: approved, flagged or needs review",
                            "Sees the reason and the decision history", "Is emailed when the auditor decides",
                            "Own spending per month and by category"]),
        ("Auditor", OK, ["Sees only what needs a person", "Rule, calculation and original document side by side",
                         "Clear to pay or reject in one click", "Notes, reopening, an append-only history",
                         "Search, filters, any employee's report"]),
        ("Management", WARN, ["Totals in AZN across AZN, USD and EUR", "Rules broken most often",
                              "Duplicates refused before they cost anything", "Time to a decision",
                              "CSV export for accounting"]),
    ]):
        x = M + i * (w3 + 20)
        d.card(x, y, w3, 290, color)
        d.text(x + 16, y - 34, head, 16, INK, bold=True)
        d.bullets(x + 16, y - 62, items, 11.5, w3 - 30, gap=5)
    d.text(M, y - 318, 'Example flag:  "1140 / 3 nights = 380 per night vs limit 300"  (EXP-1.2)', 12.5, INK, bold=True)

    # 4 ---------------------------------------------------------------- how it works
    y = d.page("The AI reads. The code decides.", "Prototype and use of AI")
    steps = [("Upload", "PDF, photo,\nemail text", BLUE), ("Duplicate?", "refused before\nany model call", BAD),
             ("AI extraction", "vendor, amount,\nnights, approvals", BLUE), ("Approval guard", "code checks the\nclaim in the text", WARN),
             ("Rules engine", "limits, tiers,\nUSD/EUR to AZN", OK), ("Verdict + trace", "rule ID and\nthe calculation", INK)]
    bw = (W - 2 * M - 5 * 14) / 6
    for i, (head, sub, color) in enumerate(steps):
        x = M + i * (bw + 14)
        d.card(x, y, bw, 104, color)
        d.text(x + 10, y - 30, head, 12, INK, bold=True)
        d.text(x + 10, y - 50, sub, 10, INK2, lead=13)
        if i < 5:
            c.setFillColor(INK3); c.setFont("Helvetica-Bold", 14); c.drawString(x + bw + 2, y - 58, ">")
    yb = y - 132
    d.card(M, yb, col, 178, BLUE)
    d.text(M + 18, yb - 30, "What the model does", 13, BLUE, bold=True)
    d.bullets(M + 18, yb - 54, ["Reads messy input: scans, photos, emails, itemised totals",
                                "English, Azerbaijani and Russian",
                                "Returns fields only; it is never asked for a verdict"], 12, col - 36)
    d.card(x2, yb, col, 178, OK)
    d.text(x2 + 18, yb - 30, "What the code does", 13, OK, bold=True)
    d.bullets(x2 + 18, yb - 54, ["Every limit, division, conversion and approval tier",
                                 "Same invoice, same verdict, exact arithmetic",
                                 "Text hidden in an invoice cannot change the outcome",
                                 "Works with no model at all on template documents"], 12, col - 36)

    # 5 ---------------------------------------------------------------- demo
    y = d.page("Live scenario: two windows, employee and auditor", "Prototype and use of AI")
    demo = [("1", "Hotel over limit", "Stamped Flagged: 1140 / 3 nights = 380 vs 300. The alert slides into the audit desk."),
            ("2", "Software in dollars", "650 USD x 1.7 = 1,105 AZN: two rules broken that the raw number hides."),
            ("3", "The same invoice again", "Duplicate, not accepted. Refused for a colleague too."),
            ("4", "Forged approval note", "The instruction to the AI inside the PDF is reported and ignored."),
            ("5", "Scanned receipt", "Read from the image by the model; sent to a person if no model is configured."),
            ("6", "Auditor decides", "Note, reject with a comment, reopen with a reason. The employee gets an email."),
            ("7", "Assistant", '"Hotel 900 AZN 2 nights" -> 450 per night, breaks EXP-1.2, at most 600 AZN fits.')]
    for i, (n, head, body) in enumerate(demo):
        yy = y - i * 46
        c.setFillColor(BLUE); c.circle(M + 14, yy - 10, 14, fill=1, stroke=0)
        c.setFillColor(white); c.setFont("Helvetica-Bold", 13); c.drawCentredString(M + 14, yy - 14.5, n)
        d.text(M + 42, yy - 6, head, 13.5, INK, bold=True)
        d.text(M + 42, yy - 24, body, 11.5, INK2)

    # 6 ---------------------------------------------------------------- testing
    y = d.page("Strict scoring: right status AND exactly the right rules", "Quality testing")
    sw = (W - 2 * M - 3 * 16) / 4
    d.stat(M, y, sw, "36/36", "Decision logic", OK, "42 cases defined; 36 run without a model")
    d.stat(M + sw + 16, y, sw, "14/36", "Spreadsheet-style filter", BAD, "our proxy for the current approach")
    d.stat(M + 2 * (sw + 16), y, sw, "29/29", "Violations cited", OK, "the filter cites 16 of 29")
    d.stat(M + 3 * (sw + 16), y, sw, "77", "Automated tests", BLUE, "roles, duplicates, history, assistant, email")
    yb = y - 140
    d.card(M, yb, W - 2 * M, 150, BLUE if live else WARN)
    if live:
        d.text(M + 18, yb - 30, f"Live model ({MODEL}) on all {live['ran']} cases, incl. free text, Azerbaijani and Russian", 13, BLUE, bold=True)
        c.setFillColor(INK); c.setFont("Courier-Bold", 30); c.drawString(M + 18, yb - 72, f"{live['passed']}/{live['ran']}")
        d.text(M + 150, yb - 56, f"strict pass   |   median {live['median_s']:.1f} s per invoice   |   ${live['cost']:.5f} per invoice   |   "
               f"${live['cost'] * 1000:.2f} per 1,000 invoices", 12.5, INK, bold=True)
        fails = ", ".join(live["failed"]) if live["failed"] else "none"
        d.text(M + 150, yb - 78, f"Failed cases: {fails}. Each failure is explained in QUALITY_TESTING.md.", 11.5, INK2, width=W - 2 * M - 170)
        d.text(M + 18, yb - 116, "The offline numbers prove the decision logic; the live run measures how well the model reads messy documents.", 11, INK3)
    else:
        d.text(M + 18, yb - 30, f"Live model ({MODEL}): not measured at the time this deck was built", 13, WARN, bold=True)
        d.text(M + 18, yb - 56, "The numbers above use the built-in reader, so they prove the decision logic, not how well a model reads a messy scan. "
               "One live extraction of an Azerbaijani hotel receipt was checked by hand and gave the expected verdict.", 12, INK2, width=W - 2 * M - 36)
    d.text(M, yb - 176, "Cases cover: limit boundaries (150/151, 500, 2000), per-night and per-person maths, approval hierarchy, USD/EUR conversion, "
           "missing data, credit notes, prompt injection, forged approvals.", 11, INK2, width=W - 2 * M)

    # 7 ---------------------------------------------------------------- what broke
    y = d.page("What broke, and what we did about it", "Quality testing")
    broke = [("A note saying \"pre-cleared by the Finance Director\" approved a 4,800 AZN payment to an unlisted vendor.",
              "Code now checks every approval claim against the document text."),
             ("A 900 AZN flight was judged as a 900 AZN hotel night.", "Wrong category alias removed; regression case added."),
             ("A refund of -240 was flagged as a 240 AZN meal; \"1.234,50\" was read as 1.2345.", "Amount parsing fixed; two cases added."),
             ("The same PDF could be submitted twice and both copies approved.", "Duplicates are refused at upload, also when re-scanned."),
             ("A second auditor could overwrite a decision without a trace.", "A decision must be reopened with a reason; history is append-only."),
             ("Our own test expected the wrong rules, and the old runner never noticed.", "The runner now compares rule IDs, not only the status.")]
    for i, (bad, fix) in enumerate(broke):
        yy = y - i * 52
        d.card(M, yy + 8, W - 2 * M, 46)
        c.setFillColor(BAD); c.rect(M, yy - 38, 5, 46, fill=1, stroke=0)
        d.text(M + 18, yy - 10, bad, 11.5, INK, bold=True)
        d.text(M + 18, yy - 27, "Fix: " + fix, 11, OK)
    d.text(M, y - 6 * 52 - 4, "24 failures are documented in QUALITY_TESTING.md, each with a fix and a test.", 11, INK3)

    # 8 ---------------------------------------------------------------- feasibility
    y = d.page("Small to run, simple to adopt", "Feasibility")
    cost_line = (f"Measured: ${live['cost']:.5f} per invoice, about ${live['cost'] * 1000:.2f} per 1,000 invoices ({MODEL})."
                 if live else f"One model call per invoice ({MODEL}: $0.75 in / $3.75 out per million tokens); a typical invoice is about 900 tokens.")
    blocks = [("Data needed", BLUE, ["The expense policy as one JSON file: limits, tiers, vendors, rates", "The invoices themselves",
                                     "No training data and no history"]),
              ("Running cost", OK, [cost_line, "A text PDF is read locally first; a duplicate is refused before any model call",
                                    "Two processes and a SQLite file on one small server"]),
              ("Where the data goes", WARN, ["Invoice content goes to the chosen model provider (Gemini, Claude or GPT)",
                                             "Files, verdicts and history stay in the company's own database",
                                             "Offline mode: nothing leaves the machine"]),
              ("Next step", INK, ["Two-week pilot with one finance team on real invoices: time per invoice, missed violations",
                                  "Confirm approvals with the approver by email or ERP",
                                  "Company sign-on, accounting connector, policy editor"])]
    bh = 152
    for i, (head, color, items) in enumerate(blocks):
        x = M + (i % 2) * (col + 28)
        yy = y - (i // 2) * (bh + 16)
        d.card(x, yy, col, bh, color)
        d.text(x + 18, yy - 28, head, 13, color if color != INK else INK, bold=True)
        d.bullets(x + 18, yy - 50, items, 11, col - 36, gap=3)

    # 9 ---------------------------------------------------------------- originality
    y = d.page("Different where it matters", "Originality")
    d.card(M, y, W - 2 * M, 62)
    d.text(M + 18, y - 26, "Today: spreadsheets and manual review, or expense suites such as Concur and Expensify that route and store claims.", 12, INK, bold=True)
    d.text(M + 18, y - 46, "FiscalAI: enforces the company's own policy on every invoice and shows the calculation, with the verdict computed by code, not by a model.", 12, BLUE, bold=True)
    points = ["The rules engine is separate from the model: auditable, reproducible, injection-resistant",
              "Approval claims are verified by code against the document text",
              "Duplicates are refused at upload, including the same invoice re-scanned into another file",
              "Currency conversion is part of the shown calculation, not a hidden step",
              "\"Needs review\" instead of a guess when data is missing or the policy is silent",
              "Separation of duties: nobody decides on their own invoice; decisions cannot be silently overwritten",
              "An assistant that computes instead of generating: \"what if\" answers come from the same engine",
              "Three languages (Azerbaijani, English, Russian), light and dark, works on a phone"]
    half = (len(points) + 1) // 2
    d.bullets(M, y - 92, points[:half], 12, col, gap=8, color=INK)
    d.bullets(x2, y - 92, points[half:], 12, col, gap=8, color=INK)

    # 10 --------------------------------------------------------------- disclosure and limits
    y = d.page("What it is built with, and its limits", "Disclosure")
    d.card(M, y, col, 300, BLUE)
    d.text(M + 18, y - 30, "Built with", 13, BLUE, bold=True)
    d.bullets(M + 18, y - 54, [f"Model: Google {MODEL} reads invoices; the verdict is never produced by a model",
                               "Data: synthetic invoices and a fictional company policy; no real or personal data",
                               "Components: FastAPI, Pydantic, pypdf, SQLite, Next.js, React, TypeScript",
                               "An AI coding assistant (Claude Code) was used to write and test the code"], 11.5, col - 36)
    d.card(x2, y, col, 300, WARN)
    d.text(x2 + 18, y - 30, "Honest limits", 13, WARN, bold=True)
    d.bullets(x2 + 18, y - 54, ["An approval is verified against the document, not the approver: a self-written \"Approved by Finance Director\" passes today",
                                "Injected instructions are detected in English only",
                                "Exchange rates are fixed policy numbers (USD 1.7, EUR 2.0)",
                                "Own accounts, not company sign-on yet",
                                "No manual time-per-invoice baseline measured yet"], 11.5, col - 36)
    d.text(M, y - 322, "Next step for the approval gap: confirm each approval with the approver by email or through the ERP.", 12, INK, bold=True)

    d.save()
    print("Wrote", OUT, "| slides:", d.n, "| live numbers:", "yes" if live else "no")


if __name__ == "__main__":
    build()
