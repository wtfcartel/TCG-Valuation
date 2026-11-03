"""Run the invoice & remittance reader over data/inbox and write:

  output/invoice_reader/ap_review_batch.xlsx     review workbook (queue, Xero lines, approvals, remittances, checks, audit)
  output/invoice_reader/xero_bills_import.csv    READY bills only, in Xero's bill-import column layout
  output/invoice_reader/approval_emails/*.eml    DRAFT approval / hold emails with the original document attached
  output/invoice_reader/invoice_reader.html      one-page review screen
  output/invoice_reader/extraction_audit.json    every extracted field, method, OCR consensus and check

    python -m demo3_invoice_reader.run
"""

from __future__ import annotations

import csv
import json
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

from common.report import OUTPUT, esc, money, page
from demo3_invoice_reader.reader import Result, run_batch

OUT = OUTPUT / "invoice_reader"
STATUS_PILL = {"READY": "GREEN", "NEEDS APPROVAL": "AMBER", "EXCEPTION": "RED"}
XERO_COLUMNS = ["ContactName", "InvoiceNumber", "Reference", "InvoiceDate", "DueDate", "Description", "Quantity",
                "UnitAmount", "AccountCode", "TaxType", "Currency"]


def name(r: Result) -> str:
    return r.supplier["supplier"] if r.supplier else (r.ext.supplier_text or "Unknown")


def value(r: Result) -> float:
    return r.ext.total or 0.0


def doc_label(r: Result) -> str:
    return f"{name(r)} {r.ext.invoice_number or ''}".strip()


# ---------------------------------------------------------------- approval emails
def draft_email(r: Result) -> EmailMessage:
    e = r.ext
    m = EmailMessage()
    m["From"] = "ap-automation@greenturf-demo.example"
    m["To"] = f"{r.approver['name']} <{r.approver['email']}>"
    if r.cc:
        m["Cc"] = ", ".join(f"{c['name']} <{c['email']}>" for c in r.cc)
    m["Date"] = formatdate(localtime=True)
    m["X-Draft-Status"] = "DRAFT - NOT SENT (demonstration)"
    if e.kind == "remittance":
        m["Subject"] = f"[Query] Short payment from {name(r)} - {e.invoice_number}"
        lines = "\n".join(f"  {x['invoice']} ({x['project_id']}): outstanding ${x['outstanding']:,.2f}, "
                          f"paid ${x['paid']:,.2f}, difference ${x['difference']:,.2f}" for x in r.remittance_matches)
        body = (f"Hi {r.approver['name'].split()[0]},\n\nA customer remittance has been received but does not clear the "
                f"invoice in full.\n\nPayer: {name(r)}\nPayment reference: {e.invoice_number}\n"
                f"Payment date: {e.invoice_date:%d/%m/%Y}\n\n{lines}\n\nPlease confirm how to treat the difference:\n"
                "  Reply ALLOCATE-PART to allocate the payment and leave the balance open, or\n"
                "  Reply QUERY to hold allocation while the customer is contacted.\n")
    else:
        if r.status == "EXCEPTION":
            m["Subject"] = f"[Hold] {doc_label(r)} ${value(r):,.2f} - {r.issues[0].split(':')[0]}"
            ask = ("This invoice has been held and will not be exported for posting.\n"
                   "  Reply RELEASE <reason> to release it, or REJECT <reason> to return it to the supplier.")
        else:
            gl_missing = not r.suggested_gl
            m["Subject"] = (f"[Approval needed] {doc_label(r)} ${value(r):,.2f} - "
                            + ("GL code required" if gl_missing else r.issues[0].split(':')[0]))
            opts = "\n".join(f"  {c['code']} {c['name']} ({c['score']:.0%}; {'; '.join(c['evidence'])})"
                             for c in r.gl_candidates) or "  (no suggestion)"
            ask = (("A GL account could not be assigned with confidence. Suggested options:\n" + opts + "\n\n")
                   if gl_missing else f"Suggested GL: {r.suggested_gl} ({r.gl_confidence:.0%}; {r.gl_reason})\n\n") + \
                  "  Reply APPROVE <GL code> to approve and code it, or REJECT <reason>."
        body = (f"Hi {r.approver['name'].split()[0]},\n\n{doc_label(r)} needs your decision before it can be posted.\n\n"
                f"Supplier: {name(r)}  (ABN {e.abn or 'not read'})\nInvoice: {e.invoice_number or 'not read'}  "
                f"dated {e.invoice_date:%d/%m/%Y}  due {e.due_date:%d/%m/%Y}\n"
                f"Amount: ${e.subtotal or 0:,.2f} + GST ${e.gst or 0:,.2f} = ${value(r):,.2f}\n"
                f"PO: {e.po_number or 'none'}   Project: {r.project_id or 'not identified'}\n\n"
                "Why this needs you:\n" + "\n".join(f"  - {i}" for i in r.issues) + "\n\n"
                + ("Also noted:\n" + "\n".join(f"  - {x}" for x in r.related) + "\n\n" if r.related else "")
                + ask + "\n")
    body += ("\n" + ("The original document is attached. " if r.cap.attachment else "")
             + "This message was drafted automatically by the AP reader and has not been sent.\n\n"
             "(Synthetic demonstration data.)")
    m.set_content(body)
    if r.cap.attachment:
        sub = "pdf" if (r.cap.attachment_name or "").endswith(".pdf") else "jpeg"
        m.add_attachment(r.cap.attachment, maintype="application" if sub == "pdf" else "image", subtype=sub,
                         filename=r.cap.attachment_name)
    return m


# ---------------------------------------------------------------- exports
def xero_rows(results: list[Result]) -> list[dict]:
    rows = []
    for r in results:
        e = r.ext
        if e.kind != "invoice" or r.status != "READY":
            continue
        for ln in e.lines:
            rows.append({"ContactName": name(r), "InvoiceNumber": e.invoice_number,
                         "Reference": " ".join(x for x in (e.po_number, r.project_id) if x),
                         "InvoiceDate": f"{e.invoice_date:%d/%m/%Y}", "DueDate": f"{e.due_date:%d/%m/%Y}",
                         "Description": ln["description"], "Quantity": 1, "UnitAmount": f"{ln['amount']:.2f}",
                         "AccountCode": r.suggested_gl, "TaxType": "GST on Expenses", "Currency": "AUD"})
    return rows


def write_workbook(results: list[Result], path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_fill, head_font = PatternFill("solid", fgColor="2F6B3F"), Font(bold=True, color="FFFFFF")
    fills = {"READY": "E3EFE5", "NEEDS APPROVAL": "FBEFD9", "EXCEPTION": "F8E1DF"}

    def sheet(title: str, headers: list[str], rows: list[list], money_cols=(), widths=None, first=False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws.append(headers)
        for c in ws[1]:
            c.fill, c.font, c.alignment = head_fill, head_font, Alignment(wrap_text=True, vertical="top")
        for row in rows:
            ws.append(row)
        for col in money_cols:
            for cell in ws[get_column_letter(col)][1:]:
                cell.number_format = '"$"#,##0.00'
        for i, w in enumerate(widths or [18] * len(headers), 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        return ws

    ws = sheet("Review queue", ["Status", "Document", "Received as", "Type", "Supplier / payer", "Invoice / ref",
                                "Invoice date", "Due", "PO", "Project", "Subtotal", "GST", "Total", "Suggested GL",
                                "GL confidence", "GL reason", "Routed to", "Issues", "Notes"],
               [[r.status, r.cap.source, r.cap.method, r.ext.kind, name(r), r.ext.invoice_number,
                 r.ext.invoice_date, r.ext.due_date, r.ext.po_number, r.project_id, r.ext.subtotal, r.ext.gst,
                 r.ext.total, r.suggested_gl or "—", r.gl_confidence, r.gl_reason,
                 r.approver["name"] if r.approver else "—", "\n".join(r.issues), "\n".join(r.related)]
                for r in results], money_cols=(11, 12, 13),
               widths=[15, 24, 24, 11, 24, 15, 12, 12, 10, 9, 13, 11, 13, 11, 10, 34, 14, 46, 46], first=True)
    for i, r in enumerate(results, 2):
        ws.cell(i, 1).fill = PatternFill("solid", fgColor=fills[r.status])
        ws.cell(i, 15).number_format = "0%"
        for c in (7, 8):
            ws.cell(i, c).number_format = "dd/mm/yyyy"

    xr = xero_rows(results)
    sheet("Xero bills (READY)", XERO_COLUMNS, [[x[c] for c in XERO_COLUMNS] for x in xr],
          widths=[26, 14, 16, 12, 12, 36, 9, 12, 12, 16, 9])
    sheet("Approvals & holds", ["Status", "Document", "Approver", "Copied", "Total", "Reason", "Email draft"],
          [[r.status, doc_label(r), r.approver["name"], ", ".join(c["name"] for c in r.cc), r.ext.total,
            "\n".join(r.issues), f"approval_emails/{Path(r.cap.source).stem}.eml"]
           for r in results if r.approver], money_cols=(5,), widths=[15, 30, 14, 22, 13, 60, 34])
    sheet("Remittances", ["Payer", "Payment ref", "Payment date", "Invoice", "Project", "Outstanding", "Paid",
                          "Difference", "Invoice age (days)", "Status"],
          [[name(r), r.ext.invoice_number, r.ext.invoice_date, m["invoice"], m["project_id"], m["outstanding"],
            m["paid"], m["difference"], m["age_days"], r.status]
           for r in results for m in r.remittance_matches], money_cols=(6, 7, 8), widths=[18, 22, 12, 11, 9, 14, 14, 13, 10, 15])
    checks = sorted({c.name for r in results for c in r.checks})
    sheet("Validation checks", ["Document"] + checks,
          [[doc_label(r)] + [next(("PASS" if c.ok else "FAIL: " + c.detail for c in r.checks if c.name == n), "n/a")
                             for n in checks] for r in results if r.ext.kind == "invoice"],
          widths=[30] + [22] * len(checks))
    sheet("Extraction audit", ["Document", "Method", "OCR confidence", "OCR passes agreeing", "Seconds"],
          [[r.cap.source, r.cap.method, round(r.cap.ocr_confidence) if r.cap.ocr_confidence else "n/a (digital)",
            ", ".join(f"{k} {v}" for k, v in r.consensus.items() if not v.startswith("0/")) or "n/a",
            round(r.seconds, 2)] for r in results], widths=[26, 30, 14, 70, 9])
    ws = wb.create_sheet("About")
    for line in ("SYNTHETIC DEMONSTRATION DATA - fictional suppliers, customers, ABNs and amounts.",
                 "Prototype output: nothing has been posted to Xero and no email has been sent.",
                 "Xero bills sheet follows the bill-import column layout; amounts are tax-exclusive line amounts.",
                 "Confirm column mapping, tax rates and account codes against the live Xero organisation before use."):
        ws.append([line])
    ws.column_dimensions["A"].width = 110
    wb.save(path)


# ---------------------------------------------------------------- review page
def render(results: list[Result]) -> str:
    n = len(results)
    cnt = {s: sum(r.status == s for r in results) for s in STATUS_PILL}
    scans = [r for r in results if r.cap.ocr_confidence is not None]
    inv = [r for r in results if r.ext.kind == "invoice"]
    auto_coded = sum(1 for r in inv if r.suggested_gl)
    held = sum(value(r) for r in results if r.status == "EXCEPTION")
    kpis = f"""<div class="grid k4">
<div class="card kpi"><div class="l">Documents read</div><div class="v">{n}</div>
<div class="s">{len(scans)} scans via OCR · {n - len(scans)} emailed / digital</div></div>
<div class="card kpi"><div class="l">Ready for review export</div><div class="v">{cnt['READY']} of {n}</div>
<div class="s">GL suggested with confidence on {auto_coded} of {len(inv)} invoices</div></div>
<div class="card kpi"><div class="l">Approval emails drafted</div><div class="v">{cnt['NEEDS APPROVAL']}</div>
<div class="s">routed to the accountable person</div></div>
<div class="card kpi"><div class="l">Held as exceptions</div><div class="v">{cnt['EXCEPTION']} · {money(held)}</div>
<div class="s">duplicate / GST error — not exported</div></div></div>"""

    rows = ""
    for r in results:
        e = r.ext
        gl = (f"<b>{esc(r.suggested_gl)}</b> <span class='note'>{r.gl_confidence:.0%}</span>" if r.suggested_gl else
              f"<span class='pill AMBER'>none</span> <span class='note'>best {esc(r.gl_candidates[0]['code'])} "
              f"{r.gl_confidence:.0%}</span>" if r.gl_candidates else "—")
        rows += (f"<tr><td><span class='pill {STATUS_PILL[r.status]}'>{esc(r.status.title())}</span></td>"
                 f"<td><b>{esc(name(r))}</b><br><span class='note'>{esc(e.invoice_number or '')} · {esc(e.kind)}</span></td>"
                 f"<td class='note'>{esc(r.cap.method)}"
                 f"{'' if r.cap.ocr_confidence is None else f'<br>OCR {r.cap.ocr_confidence:.0f}/100'}</td>"
                 f"<td class='n'>{money(value(r))}</td><td>{esc(r.project_id or '—')}</td><td>{gl}</td>"
                 f"<td>{esc(r.approver['name']) if r.approver else '—'}</td>"
                 f"<td class='note'>{'<br>'.join(esc(i) for i in r.issues) or 'All checks passed'}"
                 f"{''.join('<br><i>' + esc(x) + '</i>' for x in r.related)}</td></tr>")
    queue = f"""<h2>Review queue</h2><table><tr><th>Status</th><th>Document</th><th>Captured by</th><th class='n'>Total</th>
<th>Project</th><th>Suggested GL</th><th>Routed to</th><th>Why / notes</th></tr>{rows}</table>"""

    focus = next(r for r in results if r.status == "NEEDS APPROVAL" and not r.suggested_gl)
    em = draft_email(focus)
    email_box = f"""<h2>Example: GL could not be assigned → approval email drafted</h2>
<div class="grid k2"><div class="card"><h3>What the reader found</h3>
<table><tr><th>Field</th><th>Read as</th><th>OCR passes agreeing</th></tr>
{''.join(f"<tr><td>{esc(k.replace('_', ' '))}</td><td>{esc(getattr(focus.ext, k))}</td><td>{esc(v)}</td></tr>"
          for k, v in focus.consensus.items() if not v.startswith('0/'))}</table>
<p class="note">GL candidates: {'; '.join(f"{esc(c['code'])} {esc(c['name'])} {c['score']:.0%} ({esc('; '.join(c['evidence']))})"
                                         for c in focus.gl_candidates)}</p></div>
<div class="card"><h3>Draft email (not sent)</h3><p class="note"><b>To:</b> {esc(em['To'])}<br><b>Cc:</b> {esc(em['Cc'] or '—')}<br>
<b>Subject:</b> {esc(em['Subject'])}<br><b>Attachment:</b> {esc(focus.cap.attachment_name)}</p>
<pre style="white-space:pre-wrap;font-size:12px;background:#f3f4f1;padding:10px;border-radius:6px">{esc(em.get_body(('plain',)).get_content())}</pre></div></div>"""

    checks = sorted({c.name for r in inv for c in r.checks})
    mrows = "".join(f"<tr><td>{esc(doc_label(r))}</td>" + "".join(
        (lambda c: "<td class='note'>—</td>" if c is None else
         f"<td><span class='pill {'GREEN' if c.ok else 'RED' if c.blocking == 'EXCEPTION' else 'AMBER'}'>"
         f"{'✓' if c.ok else '✗'}</span></td>")(next((c for c in r.checks if c.name == k), None)) for k in checks)
        + "</tr>" for r in inv)
    matrix = f"""<h2>Controls applied to every invoice</h2><table><tr><th>Invoice</th>{''.join(f'<th>{esc(k)}</th>' for k in checks)}</tr>{mrows}</table>"""

    measure = """<h2>What I would measure (baseline first, in Days 1–30)</h2><table>
<tr><th>Measure</th><th>How</th></tr>
<tr><td>Minutes per invoice, receipt to approved</td><td>Time a sample of current manual processing before any change</td></tr>
<tr><td>Share of invoices coded without manual input</td><td>READY ÷ invoices received, weekly</td></tr>
<tr><td>Exception rate and value held</td><td>Duplicates, GST errors and PO overruns caught before posting</td></tr>
<tr><td>Approval turnaround</td><td>Hours from draft email to approver decision</td></tr>
<tr><td>Coding corrections after posting</td><td>Journals reversing a suggested GL — the accuracy test</td></tr></table>
<p class="note">No time saving is claimed here: it depends on Green Turf's current volume and process, which I would measure first.</p>"""
    secs = sum(r.seconds for r in results)
    footer = f"<p class='note'>This run: {n} documents processed in {secs:.1f} seconds on a laptop-class machine.</p>"
    return page("AP Invoice & Remittance Reader", "Flagship demo · OCR → validate → suggest GL → route for approval → review export",
                kpis + queue + email_box + matrix + measure + footer)


def main() -> list[Result]:
    results = run_batch()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "approval_emails").mkdir(exist_ok=True)
    for f in (OUT / "approval_emails").iterdir():
        f.unlink()
    for r in results:
        if r.approver:
            (OUT / "approval_emails" / f"{Path(r.cap.source).stem}.eml").write_bytes(bytes(draft_email(r)))
    with (OUT / "xero_bills_import.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, XERO_COLUMNS)
        w.writeheader()
        w.writerows(xero_rows(results))
    write_workbook(results, OUT / "ap_review_batch.xlsx")
    (OUT / "invoice_reader.html").write_text(render(results), encoding="utf-8")
    audit = [{"document": r.cap.source, "method": r.cap.method, "ocr_confidence": r.cap.ocr_confidence,
              "consensus": r.consensus, "status": r.status, "fields": {k: str(v) for k, v in vars(r.ext).items()},
              "checks": [vars(c) for c in r.checks], "gl_candidates": r.gl_candidates, "suggested_gl": r.suggested_gl,
              "gl_confidence": r.gl_confidence, "issues": r.issues, "related": r.related,
              "remittance_matches": r.remittance_matches, "seconds": round(r.seconds, 3)} for r in results]
    (OUT / "extraction_audit.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    cnt = {s: sum(r.status == s for r in results) for s in STATUS_PILL}
    print(f"Demo 3: {len(results)} documents → {cnt}; {len(xero_rows(results))} Xero lines; "
          f"{sum(1 for r in results if r.approver)} email drafts; {sum(r.seconds for r in results):.1f}s")
    return results


if __name__ == "__main__":
    main()
