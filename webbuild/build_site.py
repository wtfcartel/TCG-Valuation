"""Assemble the deployable static site in /public from the generated demo pages.

    python -m webbuild.build_site     (after ./run_all.sh)

Vercel serves /public as static files and /api/*.py as Python functions. No build step runs on Vercel.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from common.report import OUTPUT, ROOT, page

PUBLIC = ROOT / "public"
SITE = ROOT / "webbuild"

NAV = """<nav style="display:flex;gap:6px;flex-wrap:wrap;margin:0 0 14px;font-size:13px">
<a href="/" style="padding:4px 10px;border:1px solid var(--line);border-radius:14px;color:var(--ink);text-decoration:none;background:#fff">Overview</a>
<a href="/reader.html" style="padding:4px 10px;border:1px solid var(--line);border-radius:14px;color:var(--ink);text-decoration:none;background:#fff">Invoice reader — try it</a>
<a href="/invoice-reader-batch.html" style="padding:4px 10px;border:1px solid var(--line);border-radius:14px;color:var(--ink);text-decoration:none;background:#fff">Batch results</a>
<a href="/project-control.html" style="padding:4px 10px;border:1px solid var(--line);border-radius:14px;color:var(--ink);text-decoration:none;background:#fff">Margin early-warning</a>
<a href="/plant-allocation.html" style="padding:4px 10px;border:1px solid var(--line);border-radius:14px;color:var(--ink);text-decoration:none;background:#fff">Plant allocation</a>
<a href="/power-bi.html" style="padding:4px 10px;border:1px solid var(--line);border-radius:14px;color:var(--ink);text-decoration:none;background:#fff">Power BI feeds</a>
</nav>"""

SAMPLES = [
    ("meridian_MSC-0042", "Consultant invoice — no GL, new supplier", "Needs approval"),
    ("bayside_BPH-4436", "Plant hire — over its purchase order", "Needs approval / hold"),
    ("greenline_GIS-3307", "Irrigation parts — GST error", "Held"),
    ("bayside_BPH-4410", "Plant hire — already processed", "Held (duplicate)"),
    ("pitchline_PSS-20915", "Synthetic turf supply on PO", "Ready"),
    ("kerrigan_KQ-5520", "Crushed rock on PO", "Ready"),
    ("southway_SF-77812", "Bulk diesel, no PO", "Ready"),
    ("torque_TH-1187", "Hydraulic repair to EX20-01", "Ready"),
    ("eastvale_remittance", "Customer remittance", "Matched"),
]


def with_nav(html: str) -> str:
    return html.replace('<div class="wrap">', '<div class="wrap">' + NAV, 1)


def reader_page() -> str:
    buttons = "".join(
        f"<button class='sample' data-src='/samples/{s}.jpg' data-name='{s}.jpg'><b>{t}</b><span>{x}</span></button>"
        for s, t, x in SAMPLES)
    body = f"""
<style>
.sample{{display:flex;flex-direction:column;align-items:flex-start;gap:2px;text-align:left;padding:9px 11px;border:1px solid var(--line);
border-radius:8px;background:#fff;cursor:pointer;font:inherit;color:var(--ink)}}.sample:hover{{border-color:var(--green)}}
.sample span{{font-size:12px;color:var(--muted)}}.samples{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
@media(max-width:800px){{.samples{{grid-template-columns:1fr}}}}
#progress{{font-size:13px;color:var(--muted);min-height:20px;margin:8px 0}}
textarea{{width:100%;min-height:120px;font:12px ui-monospace,Menlo,monospace;padding:8px;border:1px solid var(--line);border-radius:6px}}
.btn{{padding:8px 14px;border-radius:6px;border:1px solid var(--green);background:var(--green);color:#fff;font:inherit;cursor:pointer}}
pre.mail{{white-space:pre-wrap;font-size:12px;background:#f3f4f1;padding:10px;border-radius:6px;margin:0}}
#preview{{max-width:100%;max-height:340px;border:1px solid var(--line);border-radius:6px;display:none}}
</style>
<div class="grid k2">
<div class="card"><h3>1 · Pick a sample scan, or upload your own image</h3>
<div class="samples">{buttons}</div>
<p style="margin:12px 0 6px"><input type="file" id="file" accept="image/*"></p>
<p class="note">The image is read in your browser (tesseract.js, three layout passes). Only the recognised text is sent to the
server, where the reader validates it, suggests the GL account and routes it. Nothing is stored, posted or emailed.</p>
<details><summary class="note" style="cursor:pointer">Or paste invoice text</summary>
<textarea id="paste" placeholder="Paste the text of an invoice or remittance"></textarea>
<p><button class="btn" id="pasteGo">Read pasted text</button></p></details>
<div id="progress"></div><img id="preview" alt="Document being read"></div>
<div class="card" id="result"><h3>2 · What the reader decided</h3><p class="note">Results appear here.</p></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js"></script>
<script>
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
const money = v => v == null ? '—' : '$' + Number(v).toLocaleString('en-AU', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
const pill = {{'READY':'GREEN','NEEDS APPROVAL':'AMBER','EXCEPTION':'RED'}};
let worker = null;
async function getWorker() {{
  if (worker) return worker;
  if (!window.Tesseract) throw new Error('OCR library did not load — check the connection, or paste the text instead.');
  $('#progress').textContent = 'Loading OCR engine (first time only)…';
  worker = await Tesseract.createWorker('eng', 1, {{ logger: m => {{ if (m.status === 'recognizing text')
    $('#progress').textContent = `Reading… ${{Math.round(m.progress * 100)}}%`; }} }});
  return worker;
}}
async function readImage(blob, name) {{
  $('#preview').src = URL.createObjectURL(blob); $('#preview').style.display = 'block';
  $('#result').innerHTML = '<h3>2 · What the reader decided</h3><p class="note">Working…</p>';
  try {{
    const bmp = await createImageBitmap(blob);
    const scale = Math.min(2, 3400 / Math.max(bmp.width, bmp.height));
    const cv = document.createElement('canvas'); cv.width = bmp.width * scale; cv.height = bmp.height * scale;
    const cx = cv.getContext('2d'); cx.fillStyle = '#fff'; cx.fillRect(0, 0, cv.width, cv.height);
    cx.imageSmoothingQuality = 'high'; cx.drawImage(bmp, 0, 0, cv.width, cv.height);
    const w = await getWorker(); const texts = [], confs = [];
    for (const [i, psm] of ['3', '4', '6'].entries()) {{
      $('#progress').textContent = `OCR pass ${{i + 1}} of 3…`;
      await w.setParameters({{ tessedit_pageseg_mode: psm }});
      const {{ data }} = await w.recognize(cv); texts.push(data.text); confs.push(data.confidence);
    }}
    await send(texts.join('\\n\\f'), name, Math.max(...confs));
  }} catch (e) {{ $('#progress').textContent = 'OCR failed: ' + e.message; }}
}}
async function send(text, name, conf) {{
  $('#progress').textContent = 'Validating, coding and routing…';
  const t0 = performance.now();
  const r = await fetch('/api/read', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ text, filename: name, ocrConfidence: conf }}) }});
  const d = await r.json();
  if (!r.ok) {{ $('#progress').textContent = d.error || 'Server error'; return; }}
  $('#progress').textContent = `Done in ${{((performance.now() - t0) / 1000).toFixed(1)}}s after OCR.`;
  render(d);
}}
function render(d) {{
  const rows = d.kind === 'remittance'
    ? [['Payer', d.supplier], ['Payment ref', d.invoiceNumber], ['Date', d.invoiceDate],
       ...d.remittanceMatches.map(m => [m.invoice + ' (' + m.project_id + ')', money(m.paid) + ' paid of ' + money(m.outstanding)])]
    : [['Supplier', d.supplier], ['ABN', d.abn], ['Invoice', d.invoiceNumber], ['Dated / due', (d.invoiceDate || '—') + ' / ' + (d.dueDate || '—')],
       ['PO / project', (d.poNumber || 'none') + ' / ' + (d.projectId || '—')], ['Subtotal + GST', money(d.subtotal) + ' + ' + money(d.gst)],
       ['Total', money(d.total)]];
  const gl = d.suggestedGl ? `<b>${{esc(d.suggestedGl)}}</b> at ${{Math.round(d.glConfidence * 100)}}% — ${{esc(d.glReason)}}`
    : (d.glCandidates.length ? 'Not assigned. Options: ' + d.glCandidates.map(c => `${{esc(c.code)}} ${{esc(c.name)}} (${{Math.round(c.score * 100)}}%)`).join('; ') : '—');
  const checks = d.checks.map(c => `<span class="pill ${{c.ok ? 'GREEN' : (c.blocking === 'EXCEPTION' ? 'RED' : 'AMBER')}}" title="${{esc(c.detail)}}">${{c.ok ? '✓' : '✗'}} ${{esc(c.name)}}</span>`).join(' ');
  let html = `<h3>2 · What the reader decided</h3><p><span class="pill ${{pill[d.status]}}" style="font-size:13px">${{esc(d.status)}}</span>
   ${{d.routedTo ? ' → routed to <b>' + esc(d.routedTo) + '</b>' : ' → ready for the review export'}}</p>
   <table>${{rows.map(r => `<tr><th style="width:34%">${{esc(r[0])}}</th><td>${{esc(r[1] ?? '—')}}</td></tr>`).join('')}}
   <tr><th>Suggested GL</th><td>${{gl}}</td></tr></table>
   <p style="margin:10px 0 4px">${{checks}}</p>
   ${{d.issues.length ? '<p class="note"><b>Why:</b> ' + d.issues.map(esc).join('<br>') + '</p>' : ''}}
   ${{d.related.length ? '<p class="note"><i>' + d.related.map(esc).join('<br>') + '</i></p>' : ''}}`;
  if (d.email) html += `<h3 style="margin-top:14px">Approval email drafted (not sent)</h3><p class="note"><b>To:</b> ${{esc(d.email.to)}}
   ${{d.email.cc ? '<br><b>Cc:</b> ' + esc(d.email.cc) : ''}}<br><b>Subject:</b> ${{esc(d.email.subject)}}</p><pre class="mail">${{esc(d.email.body)}}</pre>`;
  $('#result').innerHTML = html;
}}
document.querySelectorAll('.sample').forEach(b => b.addEventListener('click', async () => {{
  const r = await fetch(b.dataset.src); readImage(await r.blob(), b.dataset.name); }}));
$('#file').addEventListener('change', e => {{ const f = e.target.files[0]; if (f) readImage(f, f.name); }});
$('#pasteGo').addEventListener('click', () => {{ const t = $('#paste').value; if (t.trim()) send(t, 'pasted text', null); }});
</script>"""
    return page("AP Invoice Reader — Live", "Read a scanned invoice or remittance, validate it, suggest the GL, route it", body)


def landing() -> str:
    cards = [
        ("/reader.html", "Invoice & remittance reader — try it live",
         "Pick a sample scan or upload an image. The reader extracts the fields, validates ABN, GST, PO and duplicates, "
         "suggests the GL account, and drafts an approval email when it isn't sure."),
        ("/invoice-reader-batch.html", "Reader batch results",
         "Ten emailed and scanned documents: 5 ready, 3 approval emails drafted, 2 held ($23,003)."),
        ("/project-control.html", "Project margin early-warning",
         "Forecast margin at completion, exceptions with owners and due dates, tamper-evident action trail."),
        ("/plant-allocation.html", "Plant & operator allocation",
         "Lowest-cost weekly plan across owned fleet and hire, gated by tickets, inductions and service windows."),
        ("/power-bi.html", "Power BI data feeds",
         "Live CSV/JSON feeds for Power BI Desktop or Excel (Get Data → Web). Recalculated on every refresh."),
    ]
    html = "<div class='grid k2'>" + "".join(
        f"<a class='card' href='{u}' style='text-decoration:none;color:inherit'><h3>{t} →</h3><p class='note' style='margin:0'>{d}</p></a>"
        for u, t, d in cards) + "</div>"
    html += """<h2>What this is</h2><p style="max-width:760px">Working prototypes prepared for a Business Operations Director
interview. They show how targeted automation could give management better visibility, remove repetitive work and
improve the speed and quality of decisions. They are demonstrations on invented data, not implemented systems, and they
make no claim about any company's current performance.</p>"""
    return page("Business Modernisation Prototypes", "James Fischer-Myall · LogisticsDx", html)


def power_bi() -> str:
    feeds = [
        ("projects", "One row per project: contract value, % complete, CPI, forecast cost and margin, fade, unbilled work, slip"),
        ("exceptions", "Exceptions register: severity, finding, owner, escalation, due date, status"),
        ("margin_history", "Monthly forecast margin for the early-warning example project"),
        ("debtor_ageing", "Unpaid invoices by age bucket"),
        ("ap_queue", "Last reader batch: status, supplier, totals, suggested GL and confidence, issues"),
        ("plant_plan", "Next week's allocation: owned vs hire, cost and hire alternative"),
        ("plant_fleet", "8-week utilisation, breakdowns, contribution by machine"),
        ("plant_actions", "Compliance and fleet actions with owners"),
    ]
    rows = "".join(f"<tr><td class='mono'>{t}</td><td>{d}</td><td><a href='/api/powerbi?table={t}&format=csv'>CSV</a> · "
                   f"<a href='/api/powerbi?table={t}&format=json'>JSON</a></td></tr>" for t, d in feeds)
    body = f"""<h2>Connect Power BI Desktop (free) or Excel</h2><ol>
<li>Power BI Desktop → <b>Get data → Web</b> (Excel: <b>Data → From Web</b>).</li>
<li>Paste a feed URL, e.g. <code class="mono" id="example"></code></li>
<li>Choose <b>Anonymous</b> access, then <b>Load</b>. Repeat for each table and relate them on <span class="mono">project_id</span>.</li>
<li><b>Refresh</b> re-runs the calculations on the server, so a change to the source data flows straight into the report.</li></ol>
<h2>Feeds</h2><table><tr><th>Table</th><th>Contents</th><th>Download</th></tr>{rows}</table>
<h2>Next step: embedding a Power BI report here</h2><p style="max-width:760px">The same feeds can sit behind a Power BI report
embedded in this site with Microsoft's <span class="mono">powerbi-client-react</span>. Embedding for viewers who don't sign
in needs Power BI Embedded or Fabric capacity; embedding for signed-in staff uses their Power BI licences. Which route fits
depends on the business's Microsoft 365 licensing, so I would confirm that before choosing.</p>
<p class="note">Feeds are public and contain synthetic data only. Real data would sit behind authentication.</p>
<script>document.getElementById('example').textContent = location.origin + '/api/powerbi?table=projects&format=csv';</script>"""
    return page("Power BI Data Feeds", "Live tables for Power BI Desktop, the Power BI service or Excel", body)


def main() -> None:
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    (PUBLIC / "samples").mkdir(parents=True)
    (PUBLIC / "downloads").mkdir()
    (PUBLIC / "index.html").write_text(with_nav(landing()), encoding="utf-8")
    (PUBLIC / "reader.html").write_text(with_nav(reader_page()), encoding="utf-8")
    (PUBLIC / "power-bi.html").write_text(with_nav(power_bi()), encoding="utf-8")
    for src, dst in ((OUTPUT / "invoice_reader" / "invoice_reader.html", "invoice-reader-batch.html"),
                     (OUTPUT / "project_control.html", "project-control.html"),
                     (OUTPUT / "plant_allocation.html", "plant-allocation.html")):
        (PUBLIC / dst).write_text(with_nav(src.read_text(encoding="utf-8")), encoding="utf-8")
    for f in (SITE / "samples").glob("*.jpg"):
        shutil.copy(f, PUBLIC / "samples" / f.name)
    for f in ("ap_review_batch.xlsx", "xero_bills_import.csv"):
        shutil.copy(OUTPUT / "invoice_reader" / f, PUBLIC / "downloads" / f)
    print("Site written to", PUBLIC, "-", sum(1 for _ in PUBLIC.rglob("*") if _.is_file()), "files")


if __name__ == "__main__":
    main()
