"""POST /api/read — run the AP reader's extraction, validation, GL suggestion and routing on OCR text.

The browser does the OCR (tesseract.js) and sends {"text": ..., "filename": ..., "ocrConfidence": ...}.
Standard library only. Synthetic reference data; nothing is posted or sent.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo3_invoice_reader.reader import load_reference, process_text  # noqa: E402
from demo3_invoice_reader.run import draft_email, name  # noqa: E402

MAX_BYTES = 200_000
REF = load_reference()


def result_json(r) -> dict:
    e = r.ext
    out = {
        "status": r.status, "kind": e.kind, "supplier": name(r), "abn": e.abn, "invoiceNumber": e.invoice_number,
        "invoiceDate": e.invoice_date.isoformat() if e.invoice_date else None,
        "dueDate": e.due_date.isoformat() if e.due_date else None, "poNumber": e.po_number, "reference": e.reference,
        "projectId": r.project_id, "subtotal": e.subtotal, "gst": e.gst, "total": e.total,
        "lines": e.lines, "paid": e.paid, "suggestedGl": r.suggested_gl, "glConfidence": r.gl_confidence,
        "glReason": r.gl_reason, "glCandidates": r.gl_candidates,
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail, "blocking": c.blocking} for c in r.checks],
        "issues": r.issues, "related": r.related, "remittanceMatches": r.remittance_matches,
        "routedTo": r.approver["name"] if r.approver else None, "seconds": round(r.seconds, 3),
    }
    if r.approver:
        m = draft_email(r)
        out["email"] = {"to": m["To"], "cc": m["Cc"], "subject": m["Subject"],
                        "body": m.get_body(("plain",)).get_content(), "status": "DRAFT - NOT SENT"}
    return out


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send(200, {"usage": "POST JSON {text, filename?, ocrConfidence?} to read an invoice or remittance",
                         "data": "synthetic demonstration reference data"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BYTES:
            return self._send(413 if length > MAX_BYTES else 400, {"error": "send 1 to 200,000 bytes of JSON"})
        try:
            req = json.loads(self.rfile.read(length))
            text = str(req.get("text") or "").strip()
            if len(text) < 20:
                return self._send(400, {"error": "no readable text"})
            conf = req.get("ocrConfidence")
            r = process_text(text, source=str(req.get("filename") or "upload")[:120],
                             method="Browser OCR (tesseract.js)" if conf is not None else "Pasted text",
                             ocr_confidence=float(conf) if conf is not None else None, ref=REF)
            return self._send(200, result_json(r))
        except (ValueError, KeyError, TypeError) as exc:
            return self._send(400, {"error": f"could not read request: {exc}"})
