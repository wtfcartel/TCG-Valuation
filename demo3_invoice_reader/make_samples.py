"""Generate the synthetic inbox: supplier invoices and customer remittances as they would actually arrive —
digital PDFs attached to emails, scanned paper (rotated, noisy JPEGs), and a remittance typed into an email body.

Every supplier, ABN, amount and person is fictional. Run:  python -m demo3_invoice_reader.make_samples
"""

from __future__ import annotations

import random
import subprocess
import tempfile
from email.message import EmailMessage
from pathlib import Path

from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from common.report import DATA

INBOX = DATA / "inbox"
BILL_TO = ["Green Turf (demonstration)", "Accounts Payable", "Melbourne VIC"]

DOCS = [
    # file stem, delivery, supplier, abn, address, number, date, due, po, lines[(desc, qty, unit, price)], gst_override
    dict(stem="pitchline_PSS-20915", delivery="email_pdf", kind="invoice", supplier="Pitchline Synthetic Surfaces",
         abn="49 624 595 711", addr="14 Fibre Way, Dandenong South VIC", number="PSS-20915", date="27/10/2026",
         due="26/11/2026", po="PO-3021", ref="Northfield Reserve",
         lines=[("Synthetic turf 60mm football system", 7200, "m2", 21.50),
                ("Rubber crumb infill", 52, "tonne", 590.00)]),
    dict(stem="southway_SF-77812", delivery="scan", kind="invoice", supplier="Southway Fuels", abn="85 661 250 090",
         addr="2 Depot Rd, Laverton North VIC", number="SF-77812", date="24/10/2026", due="07/11/2026", po="",
         ref="Bulk tank delivery", lines=[("Diesel bulk delivery", 4200, "litre", 1.92), ("AdBlue 20L drums", 6, "ea", 38.00)]),
    dict(stem="bayside_BPH-4410", delivery="email_pdf", kind="invoice", supplier="Bayside Plant Hire",
         abn="73 569 568 058", addr="88 Quarry Ln, Braeside VIC", number="BPH-4410", date="17/10/2026", due="16/11/2026",
         po="PO-3034", ref="Northfield Reserve", lines=[("20t excavator wet hire incl. operator", 5, "day", 1650.00),
                                                         ("Float delivery and collection", 2, "ea", 400.00)]),
    dict(stem="bayside_BPH-4436", delivery="scan", kind="invoice", supplier="Bayside Plant Hire", abn="73 569 568 058",
         addr="88 Quarry Ln, Braeside VIC", number="BPH-4436", date="30/10/2026", due="29/11/2026", po="PO-3034",
         ref="Northfield Reserve", lines=[("20t excavator wet hire incl. operator", 10, "day", 1650.00),
                                          ("Float delivery and collection", 2, "ea", 400.00)]),
    dict(stem="kerrigan_KQ-5520", delivery="email_pdf", kind="invoice", supplier="Kerrigan Quarries",
         abn="31 023 281 556", addr="Lot 4 Ridge Rd, Lysterfield VIC", number="KQ-5520", date="28/10/2026",
         due="27/11/2026", po="PO-3040", ref="Westmead hockey centre",
         lines=[("20mm Class 2 crushed rock", 960, "tonne", 34.50), ("Cartage", 32, "load", 165.00)]),
    dict(stem="torque_TH-1187", delivery="scan", kind="invoice", supplier="Torque Hydraulics", abn="14 281 152 896",
         addr="5/61 Industrial Dr, Moorabbin VIC", number="TH-1187", date="22/10/2026", due="21/11/2026", po="",
         ref="EX20-01 boom cylinder", lines=[("Hydraulic boom cylinder reseal kit", 1, "ea", 1840.00),
                                              ("Workshop labour - hydraulic repair", 14, "hr", 135.00),
                                              ("Hose assembly replacement", 3, "ea", 212.00)]),
    dict(stem="meridian_MSC-0042", delivery="scan", kind="invoice", supplier="Meridian Site Consulting",
         abn="20 052 172 123", addr="Level 2, 40 Collins St, Melbourne VIC", number="MSC-0042", date="29/10/2026",
         due="12/11/2026", po="", ref="Northfield Reserve",
         lines=[("Site assessment and geotechnical report", 1, "ea", 6400.00),
                ("Additional field testing - subgrade", 1, "ea", 1850.00)]),
    dict(stem="greenline_GIS-3307", delivery="email_pdf", kind="invoice", supplier="Greenline Irrigation Supply",
         abn="73 628 587 013", addr="9 Valve St, Keysborough VIC", number="GIS-3307", date="26/10/2026", due="25/11/2026",
         po="PO-3052", ref="Eastvale College", lines=[("Solenoid valve 50mm", 20, "ea", 310.00),
                                                       ("PVC lateral pipe 40mm", 600, "m", 9.33)],
         gst_override=1250.00),
    dict(stem="eastvale_remittance", delivery="scan", kind="remittance", supplier="Eastvale College",
         addr="Finance Office, Eastvale VIC", number="RA-88213", date="30/10/2026",
         paid=[("INV-5524", 180000.00)]),
    dict(stem="council_remittance", delivery="email_body", kind="remittance", supplier="Demo Council",
         number="EFT-2026-10-31-114", date="31/10/2026", paid=[("INV-5530", 500000.00)]),
]


def amounts(doc: dict) -> tuple[float, float, float]:
    sub = round(sum(q * p for _, q, _, p in doc["lines"]), 2)
    gst = doc.get("gst_override", round(sub * 0.10, 2))
    return sub, gst, round(sub + gst, 2)


def draw_invoice(c: canvas.Canvas, doc: dict, style: int) -> None:
    W, H = A4
    font, bold = ("Helvetica", "Helvetica-Bold") if style % 2 == 0 else ("Times-Roman", "Times-Bold")
    c.setFont(bold, 18)
    c.drawString(20 * mm, H - 25 * mm, doc["supplier"])
    c.setFont(font, 10)
    c.drawString(20 * mm, H - 31 * mm, doc["addr"])
    c.drawString(20 * mm, H - 36 * mm, f"ABN {doc['abn']}")
    c.setFont(bold, 16)
    c.drawRightString(W - 20 * mm, H - 25 * mm, "TAX INVOICE")
    c.setFont(font, 10)
    y = H - 33 * mm
    for label, val in (("Invoice No:", doc["number"]), ("Invoice Date:", doc["date"]), ("Due Date:", doc["due"]),
                       ("PO Number:", doc["po"] or "-"), ("Reference:", doc["ref"])):
        c.drawRightString(W - 50 * mm, y, label)
        c.drawRightString(W - 20 * mm, y, val)
        y -= 5 * mm
    y = H - 62 * mm
    c.setFont(bold, 10)
    c.drawString(20 * mm, y, "Bill To")
    c.setFont(font, 10)
    for i, line in enumerate(BILL_TO):
        c.drawString(20 * mm, y - (i + 1) * 5 * mm, line)
    y = H - 92 * mm
    c.setFont(bold, 10)
    for x, t, right in ((20, "Description", False), (125, "Qty", True), (150, "Unit Price", True), (190, "Amount", True)):
        (c.drawRightString if right else c.drawString)(x * mm, y, t)
    c.line(20 * mm, y - 2 * mm, 190 * mm, y - 2 * mm)
    c.setFont(font, 10)
    y -= 8 * mm
    for desc, q, unit, p in doc["lines"]:
        c.drawString(20 * mm, y, desc)
        c.drawRightString(125 * mm, y, f"{q:,} {unit}")
        c.drawRightString(150 * mm, y, f"${p:,.2f}")
        c.drawRightString(190 * mm, y, f"${q * p:,.2f}")
        y -= 7 * mm
    sub, gst, tot = amounts(doc)
    y -= 6 * mm
    for label, v, f in (("Subtotal", sub, font), ("GST", gst, font), ("Total AUD", tot, bold)):
        c.setFont(f, 11)
        c.drawRightString(150 * mm, y, label)
        c.drawRightString(190 * mm, y, f"${v:,.2f}")
        y -= 6 * mm
    c.setFont(font, 9)
    c.drawString(20 * mm, 30 * mm, "Payment by EFT: please quote the invoice number as reference.")
    c.drawString(20 * mm, 20 * mm, "Synthetic sample document for demonstration - fictional supplier.")


def draw_remittance(c: canvas.Canvas, doc: dict) -> None:
    W, H = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, H - 25 * mm, f"{doc['supplier']} - Remittance Advice")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, H - 32 * mm, doc["addr"])
    c.drawString(20 * mm, H - 42 * mm, f"Payment Reference: {doc['number']}")
    c.drawString(20 * mm, H - 48 * mm, f"Payment Date: {doc['date']}")
    c.drawString(20 * mm, H - 54 * mm, "Paid To: Green Turf (demonstration)")
    y = H - 70 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Your Invoice")
    c.drawRightString(190 * mm, y, "Amount Paid")
    c.setFont("Helvetica", 10)
    for inv, amt in doc["paid"]:
        y -= 7 * mm
        c.drawString(20 * mm, y, inv)
        c.drawRightString(190 * mm, y, f"${amt:,.2f}")
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Total Paid")
    c.drawRightString(190 * mm, y, f"${sum(a for _, a in doc['paid']):,.2f}")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, 20 * mm, "Synthetic sample document for demonstration - fictional organisation.")


def to_scan(pdf: Path, out: Path, seed: int) -> None:
    """Make a believable scan: 150 dpi greyscale, slight skew, blur and speckle, saved as a lossy JPEG."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "150", "-gray", "-png", "-singlefile", str(pdf), f"{tmp}/p"], check=True)
        img = Image.open(f"{tmp}/p.png").convert("L")
    rnd = random.Random(seed)
    img = img.rotate(rnd.uniform(-1.2, 1.2), expand=True, fillcolor=255, resample=Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    px = img.load()
    w, h = img.size
    for _ in range(w * h // 400):
        x, y = rnd.randrange(w), rnd.randrange(h)
        px[x, y] = rnd.choice((0, 90, 200))
    img.point(lambda v: min(255, int(v * 0.93 + 14))).save(out, "JPEG", quality=62)


def email(path: Path, sender: str, subject: str, body: str, attachment: Path | None = None) -> None:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, "accounts@greenturf-demo.example", subject
    m["Date"] = "Fri, 31 Oct 2026 09:12:00 +1100"
    m.set_content(body)
    if attachment:
        m.add_attachment(attachment.read_bytes(), maintype="application", subtype="pdf", filename=attachment.name)
    path.write_bytes(bytes(m))


def main() -> None:
    INBOX.mkdir(parents=True, exist_ok=True)
    for f in INBOX.iterdir():
        f.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        for i, doc in enumerate(DOCS):
            if doc["delivery"] == "email_body":
                lines = "\n".join(f"  Invoice {inv}    ${amt:,.2f}" for inv, amt in doc["paid"])
                email(INBOX / f"{doc['stem']}.eml", "payments@democouncil.example",
                      f"Remittance advice {doc['number']}",
                      f"Remittance Advice\n\nPayer: {doc['supplier']}\nPayment Reference: {doc['number']}\n"
                      f"Payment Date: {doc['date']}\n\nInvoices paid:\n{lines}\n\n"
                      f"Total Paid: ${sum(a for _, a in doc['paid']):,.2f}\n\n(Synthetic sample - fictional organisation.)")
                continue
            pdf = Path(tmp) / f"{doc['stem']}.pdf"
            c = canvas.Canvas(str(pdf), pagesize=A4)
            draw_remittance(c, doc) if doc["kind"] == "remittance" else draw_invoice(c, doc, i)
            c.save()
            if doc["delivery"] == "scan":
                to_scan(pdf, INBOX / f"{doc['stem']}.jpg", seed=i)
            else:
                pdf_out = INBOX / pdf.name
                pdf_out.write_bytes(pdf.read_bytes())
                sender = next(s for s in (DATA / "finance" / "suppliers.csv").read_text().splitlines()
                              if s.startswith(doc["supplier"])).split(",")[-1]
                email(INBOX / f"{doc['stem']}.eml", sender, f"Tax invoice {doc['number']}",
                      f"Please find attached tax invoice {doc['number']}.\n\nRegards,\n{doc['supplier']}", pdf_out)
                pdf_out.unlink()  # the email is what arrives; the PDF lives inside it
    print(f"Wrote {len(list(INBOX.iterdir()))} documents to {INBOX}")


if __name__ == "__main__":
    main()
