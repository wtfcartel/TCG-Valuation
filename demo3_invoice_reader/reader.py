"""Demo 3 (flagship) — Invoice & remittance reader with GL suggestion and approval routing.

Pipeline for every document in data/inbox (emails with PDF attachments, emails with remittance text, scanned images):
  1. capture   read the PDF text layer, the email body, or OCR the scan (Tesseract), recording which method was used
  2. extract   supplier, ABN, invoice number, dates, PO, line items, subtotal, GST, total (tolerant of OCR noise)
  3. validate  ABN checksum, known supplier, GST = 10%, lines reconcile to subtotal, duplicate check, PO match and
               cumulative PO spend, OCR confidence
  4. code      suggest a GL account from three evidence sources (PO, supplier history, line-description keywords),
               with a confidence score and a plain-English reason
  5. route     READY -> review export and Xero bills import file
               NEEDS APPROVAL (GL below confidence, PO overrun) -> drafted approval email to the accountable person
               EXCEPTION (duplicate, GST error, invalid ABN, figures do not reconcile) -> drafted hold email
               Remittances are matched to open customer invoices; short payments are routed the same way.

Nothing is posted or sent. Xero and the mailbox are the integration points, represented here by an import file and
.eml drafts.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from difflib import SequenceMatcher
from email import policy
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path

# OCR and PDF libraries are imported only where documents are captured, so the extraction, validation, GL and
# routing logic can run anywhere (including a Vercel Python function that receives text OCR'd in the browser).


def _libs():
    import pdfplumber
    import pytesseract
    from PIL import Image, ImageFilter, ImageOps
    return pdfplumber, pytesseract, Image, ImageFilter, ImageOps

from common.report import DATA, REPORT_DATE, read_csv

FIN = DATA / "finance"
INBOX = DATA / "inbox"


# ---------------------------------------------------------------- reference data
def load_reference() -> dict:
    ref = {n: read_csv(FIN / f"{n}.csv") for n in
           ("chart_of_accounts", "suppliers", "purchase_orders", "ap_register", "approvers", "policy")}
    ref["policy"] = {p["setting"]: float(p["value"]) for p in ref["policy"]}
    ref["projects"] = read_csv(DATA / "projects" / "projects.csv")
    ref["variations"] = read_csv(DATA / "projects" / "variations.csv")
    ref["ar_invoices"] = read_csv(DATA / "projects" / "invoices.csv")
    ref["plant"] = read_csv(DATA / "plant" / "plant.csv")
    return ref


# ---------------------------------------------------------------- 1. capture
@dataclass
class Captured:
    source: str
    text: str
    method: str
    ocr_confidence: float | None = None
    email_from: str | None = None
    attachment: bytes | None = None
    attachment_name: str | None = None


OCR_PASSES = (("plain", "3"), ("plain", "4"), ("denoised", "4"), ("denoised", "3"))


def _prep(img: Image.Image, mode: str) -> Image.Image:
    _, _, Image, ImageFilter, ImageOps = _libs()
    g = ImageOps.grayscale(img)
    if mode == "denoised":
        g = g.resize((g.width * 2, g.height * 2), Image.LANCZOS).filter(ImageFilter.MedianFilter(3))
    return ImageOps.autocontrast(g)


def _ocr_passes(img: Image.Image) -> list[tuple[str, float]]:
    """Several OCR passes with different clean-up and page-layout settings; fields are merged afterwards."""
    pytesseract = _libs()[1]
    out = []
    for mode, psm in OCR_PASSES:
        g = _prep(img, mode)
        data = pytesseract.image_to_data(g, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
        confs = [float(c) for c, t in zip(data["conf"], data["text"]) if t.strip() and float(c) >= 0]
        lines: dict[tuple, list[str]] = {}
        for i, t in enumerate(data["text"]):
            if t.strip():
                lines.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(t)
        out.append(("\n".join(" ".join(w) for w in lines.values()), sum(confs) / len(confs) if confs else 0.0))
    return out


def _ocr(img: Image.Image) -> tuple[str, float]:
    passes = _ocr_passes(img)
    best = max(passes, key=lambda p: p[1])
    return "\n\f".join(t for t, _ in passes), best[1]


def _pdf_text(blob: bytes) -> tuple[str, str, float | None]:
    pdfplumber = _libs()[0]
    with pdfplumber.open(BytesIO(blob)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        if len(text.strip()) > 50:
            return text, "PDF text layer", None
        img = pdf.pages[0].to_image(resolution=200).original
    t, c = _ocr(img)
    return t, "OCR (image-only PDF)", c


def capture(path: Path) -> Captured:
    if path.suffix.lower() == ".eml":
        msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        for part in msg.iter_attachments():
            if part.get_content_type() == "application/pdf":
                blob = part.get_content()
                text, method, conf = _pdf_text(blob)
                return Captured(path.name, text, f"Email attachment · {method}", conf, msg["From"], blob,
                                part.get_filename())
        body = msg.get_body(preferencelist=("plain",)).get_content()
        return Captured(path.name, body, "Email body text", None, msg["From"])
    if path.suffix.lower() == ".pdf":
        blob = path.read_bytes()
        text, method, conf = _pdf_text(blob)
        return Captured(path.name, text, method, conf, attachment=blob, attachment_name=path.name)
    text, conf = _ocr(_libs()[2].open(path))
    return Captured(path.name, text, "Scanned image · OCR", conf, attachment=path.read_bytes(), attachment_name=path.name)


# ---------------------------------------------------------------- 2. extract
MONEY = r"\$?\s*([\d,]+\.\d{2})"


def _money(label: str, text: str) -> float | None:
    m = re.search(label + r"[^\d$\n]*" + MONEY, text, re.I)
    return float(m.group(1).replace(",", "")) if m else None


def _date(label: str, text: str) -> date | None:
    m = re.search(label + r"[^\d\n]*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", text, re.I)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _doc_no(prefix_label: str, text: str) -> str | None:
    # tolerant of OCR turning "MSC-0042" into "MSC:0042", "MSC 0042" or "MSC.0042"
    m = re.search(prefix_label + r"[^\n]*?\b([A-Z]{2,4})\s*[-:.\s]\s*(\d{3,6})\b", text, re.I)
    return f"{m.group(1).upper()}-{m.group(2)}" if m else None


@dataclass
class Extracted:
    kind: str
    supplier_text: str | None = None
    abn: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    po_number: str | None = None
    reference: str | None = None
    lines: list[dict] = field(default_factory=list)
    subtotal: float | None = None
    gst: float | None = None
    total: float | None = None
    asset_tags: list[str] = field(default_factory=list)
    paid: list[tuple[str, float]] = field(default_factory=list)


def extract(text: str) -> Extracted:
    if re.search(r"remittance", text, re.I):
        e = Extracted("remittance")
        m = re.search(r"Payer:\s*(.+)", text) or re.search(r"^(.+?)\s*-\s*Remittance Advice", text, re.M)
        e.supplier_text = m.group(1).strip() if m else None
        m = re.search(r"Payment Reference:\s*(\S+)", text, re.I)
        e.invoice_number = m.group(1) if m else None
        e.invoice_date = _date("Payment Date", text)
        e.paid = [(f"INV-{a}", float(b.replace(",", "")))
                  for a, b in re.findall(r"INV\s*[-:.\s]?\s*(\d{4})\D{1,40}?" + MONEY, text, re.I)]
        e.total = _money(r"(?<![A-Za-z])Total Paid", text)
        return e

    e = Extracted("invoice")
    first = next((ln for ln in text.splitlines() if re.search(r"[A-Za-z]{3}", ln)), "")
    first = re.sub(r"\bTAX INVOICE\b", "", first, flags=re.I)
    m = re.search(r"[A-Z][A-Za-z&']+(?:\s+[A-Z][A-Za-z&']+)*", first)
    e.supplier_text = m.group(0) if m else first.strip()
    m = re.search(r"ABN[:\s]*((?:\d\s*){11})", text)
    e.abn = (lambda s: f"{s[:2]} {s[2:5]} {s[5:8]} {s[8:]}")(re.sub(r"\D", "", m.group(1))) if m else None
    e.invoice_number = _doc_no(r"Invoice\s*No", text)
    e.invoice_date, e.due_date = _date(r"Invoice\s*Date", text), _date(r"Due\s*Date", text)
    m = re.search(r"PO\s*Number[:\s]*PO\s*[-:.\s]?\s*(\d{4})", text, re.I)
    e.po_number = f"PO-{m.group(1)}" if m else None
    m = re.search(r"^\s*Reference:?\s+(.+)$", text, re.I | re.M)
    e.reference = m.group(1).strip() if m else None
    e.subtotal, e.gst = _money(r"Subtotal", text), _money(r"\bGST\b", text)
    e.total = _money(r"(?<![A-Za-z])Total\s*(?:AUD)?", text)
    for ln in text.splitlines():
        amts = re.findall(r"\$\s*([\d,]+\.\d{2})", ln)
        if len(amts) >= 2 and not re.search(r"subtotal|total|gst", ln, re.I):
            desc = re.split(r"\$", ln)[0]
            desc = re.sub(r"(\s+[\d,.]+\s*[A-Za-z0-9]{0,6})+\s*$", "", desc).strip()
            toks = desc.split()
            while len(toks) > 1 and not re.fullmatch(r"[A-Za-z&'-]+", toks[-1]):
                toks.pop()  # drop OCR residue of the quantity column ("tea", "3.¢a")
            if len(toks) > 1 and toks[-1].lower() in ("tea", "lea", "ea", "hr", "day", "tonne", "litre", "load", "m"):
                toks.pop()
            desc = " ".join(toks)
            e.lines.append({"description": desc, "amount": float(amts[-1].replace(",", ""))})
    e.asset_tags = sorted(set(re.findall(r"([A-Z]{1,2}\d{2}\s?[-–—:.]\s?\d{2})\b", text)))
    return e


def _vote(values: list, valid=lambda v: True):
    vals = [v for v in values if v not in (None, "", [])]
    good = [v for v in vals if valid(v)] or vals
    if not good:
        return None, 0
    best = max(set(map(repr, good)), key=lambda r: sum(repr(v) == r for v in good))
    value = next(v for v in good if repr(v) == best)
    return value, sum(repr(v) == best for v in vals)


def extract_merged(text: str, suppliers: list[dict]) -> tuple[Extracted, dict[str, str]]:
    """Merge several OCR passes field by field. A value that passes its own check (ABN checksum, a supplier in the
    master file, lines that add up to the subtotal) is preferred; otherwise the most common reading wins.
    Returns the merged fields plus how many passes agreed on each — the consensus shown to the reviewer."""
    passes = [extract(t) for t in text.split("\n\f")]
    if len(passes) == 1:
        return passes[0], {}
    kind, _ = _vote([p.kind for p in passes])
    group = [p for p in passes if p.kind == kind]
    e, agree = Extracted(kind), {}
    names = [s["supplier"] for s in suppliers]

    def known(v: str) -> bool:
        return any(SequenceMatcher(None, n.lower(), v.lower()).ratio() > 0.85 for n in names)

    for f, check in (("supplier_text", known), ("abn", abn_valid), ("invoice_number", lambda v: True),
                     ("invoice_date", lambda v: True), ("due_date", lambda v: True), ("po_number", lambda v: True),
                     ("reference", lambda v: True), ("subtotal", lambda v: True), ("gst", lambda v: True),
                     ("total", lambda v: True)):
        v, n = _vote([getattr(p, f) for p in group], check)
        setattr(e, f, v)
        agree[f] = f"{n}/{len(group)}"
    with_lines = [p for p in group if p.lines]
    fit = [p for p in with_lines if e.subtotal is not None and abs(sum(x["amount"] for x in p.lines) - e.subtotal) < 0.05]
    described = lambda p: sum(1 for x in p.lines if len(x["description"]) >= 4)  # noqa: E731
    e.lines = (sorted(fit, key=lambda p: -described(p)) or sorted(with_lines, key=lambda p: (-described(p), -len(p.lines)))
               or [Extracted("x")])[0].lines
    e.asset_tags = sorted({t for p in group for t in p.asset_tags})
    paid_ok = [p.paid for p in group if p.paid and e.total is not None and abs(sum(a for _, a in p.paid) - e.total) < 0.05]
    e.paid = (paid_ok or [p.paid for p in group if p.paid] or [[]])[0]
    return e, agree


def match_assets(tags: list[str], plant: list[dict]) -> list[str]:
    """Match OCR'd asset references to the plant register: the numeric part must match exactly and the letter
    prefix may differ by one character (OCR reads 'EX20-01' as 'BX20-01')."""
    out = set()
    for t in tags:
        letters, nums = re.match(r"([A-Z]+)", t).group(1), re.sub(r"\D", "", t)
        for a in plant:
            a_letters, a_nums = re.match(r"([A-Z]+)", a["asset_id"]).group(1), re.sub(r"\D", "", a["asset_id"])
            if nums == a_nums and (letters == a_letters or
                                   (len(letters) == len(a_letters) and sum(x != y for x, y in zip(letters, a_letters)) <= 1)):
                out.add(a["asset_id"])
    return sorted(out)


# ---------------------------------------------------------------- 3. validate
def abn_valid(abn: str | None) -> bool:
    if not abn:
        return False
    digits = [int(c) for c in re.sub(r"\D", "", abn)]
    if len(digits) != 11:
        return False
    digits[0] -= 1
    return sum(d * w for d, w in zip(digits, (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19))) % 89 == 0


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    blocking: str | None = None  # None | "APPROVAL" | "EXCEPTION"


def validate(e: Extracted, cap: Captured, ref: dict, seen: set[tuple[str, str]]) -> tuple[list[Check], dict | None, dict | None]:
    pol = ref["policy"]
    checks: list[Check] = []
    supplier = next((s for s in ref["suppliers"] if s["abn"] == e.abn), None)
    if not supplier and e.supplier_text:
        best = max(ref["suppliers"], key=lambda s: SequenceMatcher(None, s["supplier"].lower(), e.supplier_text.lower()).ratio())
        if SequenceMatcher(None, best["supplier"].lower(), e.supplier_text.lower()).ratio() > 0.85:
            supplier = best
    abn_note = e.abn or "ABN not found"
    if supplier and e.abn != supplier["abn"] and not abn_valid(e.abn):
        # OCR misread a digit or two: reconcile to the supplier master only when the name matched AND the read ABN
        # is within two digits of the registered one. Anything further off stays an exception.
        read = re.sub(r"\D", "", e.abn or "")
        master = re.sub(r"\D", "", supplier["abn"])
        if len(read) == 11 and sum(a != b for a, b in zip(read, master)) <= 2:
            abn_note = f"{supplier['abn']} (OCR read {e.abn}; reconciled to supplier master)"
            e.abn = supplier["abn"]
    checks.append(Check("ABN checksum", abn_valid(e.abn), abn_note, None if abn_valid(e.abn) else "EXCEPTION"))
    checks.append(Check("Known supplier", bool(supplier),
                        supplier["supplier"] if supplier else "Not in supplier master — new supplier",
                        None if supplier else "APPROVAL"))
    required = {"invoice number": e.invoice_number, "invoice date": e.invoice_date, "subtotal": e.subtotal,
                "GST": e.gst, "total": e.total}
    missing = [k for k, v in required.items() if v is None]
    checks.append(Check("Required fields", not missing, "all present" if not missing else "missing: " + ", ".join(missing),
                        "EXCEPTION" if missing else None))
    if not missing:
        exp_gst = round(e.subtotal * pol["gst_rate"], 2)
        ok = abs(e.gst - exp_gst) <= pol["gst_tolerance"] and abs(e.subtotal + e.gst - e.total) <= pol["gst_tolerance"]
        checks.append(Check("GST and total", ok, f"GST ${e.gst:,.2f} vs expected ${exp_gst:,.2f}; total ${e.total:,.2f}",
                            None if ok else "EXCEPTION"))
    if e.lines and e.subtotal is not None:
        s = round(sum(x["amount"] for x in e.lines), 2)
        ok = abs(s - e.subtotal) <= 0.05
        checks.append(Check("Lines reconcile", ok, f"lines ${s:,.2f} vs subtotal ${e.subtotal:,.2f}",
                            None if ok else "EXCEPTION"))
    key = (e.abn or "", e.invoice_number or "")
    dup = any(r["supplier_abn"] == key[0] and r["invoice_number"] == key[1] for r in ref["ap_register"]) or key in seen
    checks.append(Check("Duplicate", not dup, "already in AP register" if dup else "not previously processed",
                        "EXCEPTION" if dup else None))
    po = next((p for p in ref["purchase_orders"] if p["po_number"] == e.po_number), None)
    if e.po_number:
        if not po:
            checks.append(Check("Purchase order", False, f"{e.po_number} not found", "APPROVAL"))
        else:
            prior = sum(float(r["subtotal"]) for r in ref["ap_register"]
                        if r["po_number"] == po["po_number"] and r["invoice_number"] != e.invoice_number)
            cap_ = float(po["amount_ex_gst"]) * (1 + pol["po_tolerance"])
            ok = po["supplier_abn"] == e.abn and prior + (e.subtotal or 0) <= cap_
            checks.append(Check("Purchase order", ok,
                                f"{po['po_number']} ${float(po['amount_ex_gst']):,.0f}; previously billed ${prior:,.0f} + "
                                f"this ${e.subtotal or 0:,.0f} = ${prior + (e.subtotal or 0):,.0f}"
                                + ("" if ok else f" (over by ${prior + (e.subtotal or 0) - float(po['amount_ex_gst']):,.0f})"),
                                None if ok else "APPROVAL"))
    if cap.ocr_confidence is not None:
        ok = cap.ocr_confidence >= 70
        checks.append(Check("OCR confidence", ok, f"{cap.ocr_confidence:.0f}/100", None if ok else "APPROVAL"))
    return checks, supplier, po


# ---------------------------------------------------------------- 4. code
def suggest_gl(e: Extracted, supplier: dict | None, po: dict | None, ref: dict) -> tuple[list[dict], float, str]:
    coa = {a["code"]: a for a in ref["chart_of_accounts"]}
    evidence: dict[str, list[tuple[str, float]]] = {}
    if po:
        evidence.setdefault(po["gl"], []).append((f"purchase order {po['po_number']}", 0.95))
    if supplier:
        evidence.setdefault(supplier["default_gl"], []).append(("supplier's usual account", 0.85))
    words = " ".join(x["description"] for x in e.lines).lower()
    hits = {c: [k for k in a["keywords"].split("|") if re.search(r"\b" + re.escape(k) + r"\b", words)]
            for c, a in coa.items() if c != "1200"}
    total_hits = sum(len(v) for v in hits.values())
    for c, ks in hits.items():
        if ks:
            evidence.setdefault(c, []).append((f"description mentions {', '.join(ks)}", 0.8 * len(ks) / total_hits))
    ranked = []
    for c, ev in evidence.items():
        score = min(0.99, max(s for _, s in ev) + 0.05 * (len(ev) - 1))
        ranked.append({"code": c, "name": coa[c]["name"], "score": score, "evidence": [w for w, _ in ev]})
    ranked.sort(key=lambda r: -r["score"])
    if not ranked:
        return [], 0.0, "no evidence for any account"
    conf = ranked[0]["score"]
    if len(ranked) > 1 and ranked[0]["score"] - ranked[1]["score"] < 0.15 and not po:
        conf -= 0.15 - (ranked[0]["score"] - ranked[1]["score"])  # two accounts are plausible: lower confidence
    reason = "; ".join(ranked[0]["evidence"])
    return ranked[:3], round(conf, 2), reason


# ---------------------------------------------------------------- 5. route
@dataclass
class Result:
    cap: Captured
    ext: Extracted
    status: str
    checks: list[Check] = field(default_factory=list)
    supplier: dict | None = None
    po: dict | None = None
    project_id: str | None = None
    gl_candidates: list[dict] = field(default_factory=list)
    gl_confidence: float = 0.0
    gl_reason: str = ""
    suggested_gl: str | None = None
    approver: dict | None = None
    cc: list[dict] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    remittance_matches: list[dict] = field(default_factory=list)
    consensus: dict = field(default_factory=dict)
    seconds: float = 0.0


def _approver(ref: dict, project_id: str | None) -> dict:
    by = {a["role"]: a for a in ref["approvers"]}
    return by.get(f"Project Manager {project_id}") or by["Accounts Lead"]


def _project(e: Extracted, po: dict | None, ref: dict) -> str | None:
    if po:
        return po["project_id"]
    for p in ref["projects"]:
        site = p["name"].rsplit(" ", 1)[0] if p["name"].split()[-1].lower() in ("pitch", "oval", "earthworks", "centre") else p["name"]
        if e.reference and site.lower() in e.reference.lower():
            return p["project_id"]
    return None


def process_remittance(cap: Captured, e: Extracted, ref: dict) -> Result:
    r = Result(cap, e, "READY", suggested_gl="1200", gl_confidence=0.99, gl_reason="customer remittance → receivables")
    by = {a["role"]: a for a in ref["approvers"]}
    for inv, amt in e.paid:
        ar = next((a for a in ref["ar_invoices"] if a["invoice_no"] == inv), None)
        if not ar:
            r.status, r.issues = "EXCEPTION", r.issues + [f"{inv} not found in open receivables"]
            continue
        outstanding = float(ar["amount"]) - float(ar["paid"])
        diff = round(amt - outstanding, 2)
        m = {"invoice": inv, "project_id": ar["project_id"], "outstanding": outstanding, "paid": amt, "difference": diff,
             "age_days": (REPORT_DATE - date.fromisoformat(ar["issued"])).days}
        r.remittance_matches.append(m)
        if diff < -0.05:
            r.status = "NEEDS APPROVAL"
            r.issues.append(f"{inv} short-paid by ${-diff:,.2f} (paid ${amt:,.2f} of ${outstanding:,.2f})")
            r.approver, r.cc = by["Accounts Lead"], [_approver(ref, ar["project_id"])]
        r.project_id = ar["project_id"]
    if e.total is not None and abs(sum(a for _, a in e.paid) - e.total) > 0.05:
        r.status = "EXCEPTION"
        r.issues.append("payment lines do not add to total paid")
    return r


def process(path: Path, ref: dict, seen: set) -> Result:
    t0 = time.perf_counter()
    r = process_captured(capture(path), ref, seen)
    r.seconds = time.perf_counter() - t0
    return r


def process_text(text: str, source: str = "upload", method: str = "Browser OCR", ocr_confidence: float | None = None,
                 ref: dict | None = None) -> Result:
    """Run extraction, validation, GL suggestion and routing on text that was captured elsewhere."""
    t0 = time.perf_counter()
    r = process_captured(Captured(source, text, method, ocr_confidence), ref or load_reference(), set())
    r.seconds = time.perf_counter() - t0
    return r


def process_captured(cap: Captured, ref: dict, seen: set) -> Result:
    t0 = time.perf_counter()
    e, consensus = extract_merged(cap.text, ref["suppliers"])
    if e.kind == "remittance":
        r = process_remittance(cap, e, ref)
        r.consensus = consensus
        r.seconds = time.perf_counter() - t0
        return r
    checks, supplier, po = validate(e, cap, ref, seen)
    seen.add((e.abn or "", e.invoice_number or ""))
    cands, conf, reason = suggest_gl(e, supplier, po, ref)
    r = Result(cap, e, "READY", checks, supplier, po, _project(e, po, ref), cands, conf, reason)
    r.consensus = consensus
    pol = ref["policy"]
    if cands and conf >= pol["gl_confidence_auto"]:
        r.suggested_gl = cands[0]["code"]
    else:
        r.issues.append(f"GL not confirmed — best match {cands[0]['code']} {cands[0]['name']} at {conf:.0%} confidence"
                        if cands else "no GL suggestion")
    r.issues += [f"{c.name}: {c.detail}" for c in checks if not c.ok]
    blocks = {c.blocking for c in checks if not c.ok}
    r.status = "EXCEPTION" if "EXCEPTION" in blocks else "NEEDS APPROVAL" if ("APPROVAL" in blocks or not r.suggested_gl) else "READY"
    by = {a["role"]: a for a in ref["approvers"]}
    if r.status == "EXCEPTION":
        r.approver = by["Accounts Lead"]
    elif r.status == "NEEDS APPROVAL":
        r.approver = _approver(ref, r.project_id)
        r.cc = [by["Accounts Lead"]] if r.approver["role"] != "Accounts Lead" else []
        if (e.subtotal or 0) > pol["director_threshold"]:
            r.cc.append(by["Business Operations Director"])
    words = set(re.findall(r"[a-z]{5,}", " ".join(x["description"] for x in e.lines).lower()))
    for v in ref["variations"]:
        if v["project_id"] == r.project_id and v["status"] == "pending" and words & set(re.findall(r"[a-z]{5,}", v["description"].lower())):
            r.related.append(f"May relate to pending variation {v['variation_id']} \"{v['description']}\" — "
                             "confirm whether this cost is recoverable from the client")
    assets = match_assets(e.asset_tags, ref["plant"])
    if assets:
        r.related.append(f"Asset reference read as {', '.join(e.asset_tags)} → matched to plant register {', '.join(assets)}; "
                         "cost will be tracked against the machine")
    r.seconds = time.perf_counter() - t0
    return r


def run_batch(inbox: Path = INBOX) -> list[Result]:
    ref, seen = load_reference(), set()
    return [process(p, ref, seen) for p in sorted(inbox.iterdir()) if p.suffix.lower() in (".eml", ".pdf", ".jpg", ".png")]


def parse_au_date(s: str) -> date:
    return datetime.strptime(s, "%d/%m/%Y").date()
