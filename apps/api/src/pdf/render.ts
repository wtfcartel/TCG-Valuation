import PDFDocument from "pdfkit";

type Payload = Record<string, any>;

function money(minor: number | null | undefined, currency: string): string {
  if (minor == null) return "—";
  return `${currency} ${(minor / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Standard PDF fonts use WinAnsi encoding; map the few symbols we emit that it lacks. */
function t(text: unknown): string {
  return String(text ?? "")
    .replace(/→/g, "->")
    .replace(/≥/g, ">=")
    .replace(/≤/g, "<=")
    .replace(/[^\x00-\xFF\u2013\u2014\u2018\u2019\u201C\u201D\u2022\u2026\u20AC]/g, "?");
}

class Writer {
  constructor(readonly doc: PDFKit.PDFDocument) {}

  h1(text: string) {
    this.doc.moveDown(0.5).font("Helvetica-Bold").fontSize(18).fillColor("#111").text(t(text));
    this.doc.moveDown(0.3);
  }

  h2(text: string) {
    this.ensureSpace(60);
    this.doc.moveDown(0.6).font("Helvetica-Bold").fontSize(12.5).fillColor("#1f3a5f").text(t(text));
    this.doc.moveDown(0.2).fillColor("#111");
  }

  h3(text: string) {
    this.ensureSpace(40);
    this.doc.moveDown(0.4).font("Helvetica-Bold").fontSize(10.5).fillColor("#111").text(t(text));
  }

  p(text: string, opts: { size?: number; color?: string } = {}) {
    this.doc.font("Helvetica").fontSize(opts.size ?? 9.5).fillColor(opts.color ?? "#222").text(t(text), { align: "left" });
    this.doc.moveDown(0.25);
  }

  kv(pairs: Array<[string, string]>) {
    for (const [k, v] of pairs) {
      this.doc.font("Helvetica-Bold").fontSize(9.5).fillColor("#333").text(`${t(k)}: `, { continued: true });
      this.doc.font("Helvetica").fillColor("#111").text(t(v));
    }
    this.doc.moveDown(0.3);
  }

  bullets(items: string[]) {
    for (const item of items) {
      this.doc.font("Helvetica").fontSize(9).fillColor("#222").text(`•  ${t(item)}`, { indent: 6 });
    }
    this.doc.moveDown(0.3);
  }

  table(headers: string[], rows: string[][], widths: number[]) {
    const doc = this.doc;
    const x0 = doc.page.margins.left;
    const drawRow = (raw: string[], bold: boolean) => {
      const cells = raw.map(t);
      doc.font(bold ? "Helvetica-Bold" : "Helvetica").fontSize(7.5);
      const heights = cells.map((c, i) => doc.heightOfString(c, { width: widths[i]! - 4 }));
      const h = Math.max(...heights) + 4;
      this.ensureSpace(h + 2);
      const y = doc.y;
      let x = x0;
      if (bold) doc.rect(x0, y, widths.reduce((a, b) => a + b, 0), h).fill("#eef2f7").fillColor("#111");
      cells.forEach((c, i) => {
        doc.fillColor("#111").text(c, x + 2, y + 2, { width: widths[i]! - 4 });
        x += widths[i]!;
      });
      doc.x = x0;
      doc.y = y + h;
      doc.moveTo(x0, doc.y).lineTo(x0 + widths.reduce((a, b) => a + b, 0), doc.y).lineWidth(0.3).strokeColor("#ccd").stroke();
    };
    drawRow(headers, true);
    for (const r of rows) drawRow(r, false);
    doc.moveDown(0.5);
  }

  ensureSpace(height: number) {
    if (this.doc.y + height > this.doc.page.height - this.doc.page.margins.bottom - 20) this.doc.addPage();
  }
}

function finish(doc: PDFKit.PDFDocument, footer: string): void {
  const range = doc.bufferedPageRange();
  for (let i = range.start; i < range.start + range.count; i += 1) {
    doc.switchToPage(i);
    const bottom = doc.page.margins.bottom;
    doc.page.margins.bottom = 0;
    doc
      .font("Helvetica")
      .fontSize(7)
      .fillColor("#666")
      .text(`${footer} · Page ${i + 1} of ${range.count}`, doc.page.margins.left, doc.page.height - 30, {
        width: doc.page.width - doc.page.margins.left - doc.page.margins.right,
        align: "center",
      });
    doc.page.margins.bottom = bottom;
  }
  doc.end();
}

function collect(doc: PDFKit.PDFDocument): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    doc.on("data", (c: Buffer) => chunks.push(c));
    doc.on("end", () => resolve(Buffer.concat(chunks)));
    doc.on("error", reject);
  });
}

function newDoc(title: string) {
  return new PDFDocument({
    size: "A4",
    margins: { top: 50, bottom: 50, left: 50, right: 50 },
    bufferPages: true,
    info: { Title: title, Author: "Cardcore", Creator: "Cardcore valuation engine" },
  });
}

export async function renderValuationReport(payload: Payload, meta: { sha256: string; generatedAt: string }): Promise<Buffer> {
  const doc = newDoc(`Cardcore valuation report v${payload.reportVersion}`);
  const out = collect(doc);
  const w = new Writer(doc);
  const ccy = payload.baseCurrency as string;

  w.h1("Collection Valuation Report");
  w.kv([
    ["Client", `${payload.client.name} (${payload.client.email})`],
    ["Collection", payload.client.collection],
    ["Valuation purpose", payload.purpose],
    ["Valuation date", payload.valuationDate],
    ["Base currency", ccy],
    ["Methodology version", payload.methodology.id],
    ["Report version", String(payload.reportVersion)],
    ["Generated", meta.generatedAt],
  ]);

  w.h2("Valuation conclusion");
  w.p(payload.conclusion, { size: 10.5, color: "#111" });
  w.kv([["Collection total", money(payload.collectionTotalMinor, ccy)]]);
  if (payload.unvaluedAssets.length) {
    w.p(`Not valued (insufficient evidence): ${payload.unvaluedAssets.join(", ")}`, { color: "#8a4b00" });
  }

  if (payload.evidenceProvenance) {
    w.h2("Evidence provenance");
    w.p(payload.evidenceProvenance, { color: "#8a0000" });
  }

  w.h2("Purpose and basis of value");
  w.p(payload.purposeDefinition);

  w.h2("Methodology");
  w.p(`${payload.methodology.name} (${payload.methodology.id}), effective ${payload.methodology.effective_from}.`);
  w.p(payload.methodology.summary);
  w.p(`Full methodology: ${payload.methodology.document_ref}`, { size: 8.5, color: "#555" });

  w.h2("Assumptions");
  w.bullets(payload.assumptions);
  w.h2("Limitations");
  w.bullets(payload.limitations);

  w.h2("Schedule of assets");
  w.table(
    ["Asset", "Description", "Grading", "Qty", "Unit value", "Total", "Confidence"],
    payload.assets.map((a: Payload) => [
      a.assetRef,
      a.description,
      a.grading,
      String(a.quantity),
      money(a.valuation?.concludedUnitValueMinor, ccy),
      money(a.valuation?.totalValueMinor, ccy),
      a.valuation ? `${a.valuation.confidence} evidence` : "not valued",
    ]),
    [52, 150, 70, 28, 72, 72, 51],
  );

  w.h2("Comparable-sales evidence");
  for (const a of payload.assets as Payload[]) {
    w.h3(`${a.assetRef} — ${a.description} (${a.grading})`);
    if (!a.valuation) {
      w.p("No adequate comparable sales were available; no value concluded.", { color: "#8a4b00" });
      continue;
    }
    const v = a.valuation;
    const s = v.statistics ?? {};
    w.kv([
      ["Valuation ID", v.valuationId],
      ["Method", `${v.method} (methodology ${v.methodologyVersion})`],
      [
        "Statistics",
        `n=${s.count} · mean ${money(s.meanMinor, ccy)} · median ${money(s.medianMinor, ccy)} · min ${money(s.minMinor, ccy)} · max ${money(s.maxMinor, ccy)} · range ${money(s.rangeMinor, ccy)} · dispersion ${s.dispersionPct}%`,
      ],
      ["Concluded unit value", money(v.concludedUnitValueMinor, ccy)],
      ["Confidence", `${v.confidence} evidence`],
      ["Inputs hash", v.inputsHash],
    ]);
    if (v.baseStatistics) {
      w.p(
        `Escalation: base three-sale set dispersion ${v.baseStatistics.dispersionPct}% exceeded the threshold; the set was expanded to ${s.count} transactions.`,
        { color: "#8a4b00" },
      );
    }
    w.bullets((v.confidenceReasons ?? []) as string[]);
    if ((v.flags ?? []).length) w.bullets((v.flags as Payload[]).map((f) => `Flag ${f.code}: ${f.message}`));
    w.table(
      ["Date", "Venue / source", "Reference", "Amount", "Premium", "FX", `Basis (${ccy})`, "Tier", "Dev."],
      (v.comparablesUsed as Payload[]).map((c) => [
        c.observed_at,
        `${c.venue ?? ""} [${c.source_id}]${c.licence_status === "unlicensed" ? "\nUNLICENSED/SCRAPED" : ""}`,
        `${c.source_reference}${c.source_url ? `\n${c.source_url}` : ""}`,
        money(c.amount_minor, c.currency),
        money(c.buyers_premium_minor, c.currency),
        c.fx_rate != null ? `${Number(c.fx_rate).toFixed(4)} (${c.fx_rate_date}, ${c.fx_source})` : "—",
        money(c.basis_amount_base_minor, ccy),
        c.match_tier + (c.suspected_outlier ? " (outlier?)" : ""),
        c.deviation_from_median_pct != null ? `${c.deviation_from_median_pct}%` : "",
      ]),
      [44, 62, 110, 52, 42, 64, 52, 38, 31],
    );
    const rejected = v.comparablesRejected as Payload[];
    if (rejected.length) {
      w.p(`Evidence considered and not used (${rejected.length}):`, { size: 8.5 });
      w.table(
        ["Date", "Source", "Reference", "Amount", "Reason"],
        rejected.map((c) => [
          c.observed_at,
          `${c.venue ?? ""} [${c.source_id}]`,
          c.source_reference,
          money(c.amount_minor, c.currency),
          `${c.rejection_code}: ${c.rejection_detail}`,
        ]),
        [48, 90, 120, 60, 177],
      );
    }
    for (const o of v.overrides as Payload[]) {
      w.p(
        `Manual override by ${o.overridden_by} (${o.overrider_role}) on ${o.created_at}: unit value set to ${money(o.override_unit_value_minor, ccy)}. Reason: ${o.reason}`,
        { color: "#8a0000" },
      );
    }
  }

  w.h2("Valuer");
  w.kv([
    ["Name", String(payload.valuer.name)],
    ["Role", String(payload.valuer.role)],
  ]);
  w.p(payload.valuer.statement);

  w.h2("Independent methodology review");
  w.p(payload.methodology.reviewStatement);

  w.h2("Report integrity");
  w.p(
    `This report is an immutable snapshot (schema ${payload.schemaVersion}, version ${payload.reportVersion}). SHA-256 of the canonical report payload: ${meta.sha256}`,
    { size: 8.5 },
  );

  finish(doc, `Cardcore valuation report v${payload.reportVersion} · ${meta.sha256.slice(0, 16)}`);
  return out;
}

export async function renderInsuranceReport(payload: Payload, meta: { sha256: string; generatedAt: string }): Promise<Buffer> {
  const doc = newDoc(`Cardcore insurance adjustment report v${payload.reportVersion}`);
  const out = collect(doc);
  const w = new Writer(doc);
  const ccy = payload.currency as string;

  w.h1("Insurance Adjustment Report");
  w.kv([
    ["Insurer", payload.policy.insurer ?? "—"],
    ["Policy reference", payload.policy.policyReference ?? "—"],
    ["Customer reference", payload.policy.customerReference ?? "—"],
    ["Report version", String(payload.reportVersion)],
    ["Generated", meta.generatedAt],
    ["Events covered", `#${payload.eventRange.fromSeq} – #${payload.eventRange.toSeq}`],
  ]);

  w.h2("Declared value");
  w.kv([
    ["Previous declared value", money(payload.previousDeclaredValueMinor, ccy)],
    ["Revised declared value", money(payload.revisedDeclaredValueMinor, ccy)],
    ["Net change", money(payload.netChangeMinor, ccy)],
    ["Effective date", payload.effectiveDate],
  ]);

  w.h2("Adjustment events");
  w.table(
    ["#", "Type", "Effective", "Reason", "Previous", "Revised", "Event hash"],
    (payload.adjustments as Payload[]).map((e) => [
      String(e.seq),
      e.type,
      e.effectiveDate,
      e.reason,
      money(e.previousDeclaredValueMinor, ccy),
      money(e.revisedDeclaredValueMinor, ccy),
      String(e.eventHash).slice(0, 16),
    ]),
    [20, 70, 55, 140, 70, 70, 70],
  );

  const assetTable = (title: string, rows: Payload[]) => {
    w.h2(`${title} (${rows.length})`);
    if (!rows.length) return w.p("None.");
    w.table(
      ["Asset", "Description", "Qty", "Previous", "New"],
      rows.map((r) => [r.assetRef, r.description, String(r.quantity), money(r.previousValueMinor, ccy), money(r.newValueMinor, ccy)]),
      [60, 215, 30, 90, 100],
    );
  };
  assetTable("Assets added", payload.assetsAdded);
  assetTable("Assets removed", payload.assetsRemoved);
  assetTable("Assets revalued / adjusted", payload.assetsRevalued);

  w.h2("Evidence");
  w.table(
    ["Asset", "Valuation ID", "Date", "Method", "Confidence", "n (unlic.)", "Inputs hash"],
    (payload.evidence as Payload[]).map((e) => [
      e.assetRef,
      e.valuationId,
      e.valuationDate,
      e.method,
      e.confidence,
      `${e.comparablesUsed}${e.unlicensedComparablesUsed ? ` (${e.unlicensedComparablesUsed})` : ""}`,
      String(e.inputsHash).slice(0, 16),
    ]),
    [50, 120, 50, 70, 55, 35, 115],
  );

  if (payload.evidenceProvenance) {
    w.h2("Evidence provenance");
    w.p(payload.evidenceProvenance, { color: "#8a0000" });
  }
  if (payload.methodology) {
    w.h2("Methodology");
    w.p(`${payload.methodology.name} (${payload.methodology.id}) — ${payload.methodology.documentRef}`);
    w.p(payload.methodology.reviewStatement);
  }
  w.h2("Important");
  w.p(payload.disclaimer);
  w.h2("Report integrity");
  w.p(`SHA-256 of canonical payload: ${meta.sha256}. First event hash ${payload.eventRange.firstEventHash}; last event hash ${payload.eventRange.lastEventHash}.`, {
    size: 8.5,
  });

  finish(doc, `Cardcore insurance adjustment v${payload.reportVersion} · ${meta.sha256.slice(0, 16)}`);
  return out;
}
