import { useCallback, useEffect, useState } from "react";
import { api, photoUrl, uploadPhoto } from "../api";
import { Card, ConfidenceBadge, ErrorNote, useAction } from "../components/ui";
import { label, money, toMinor, today } from "../format";

type Any = Record<string, any>;

function Photo({ id }: { id: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let url: string | null = null;
    photoUrl(id).then((u) => setSrc((url = u)));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [id]);
  return src ? <img className="photo" src={src} alt="Owner photograph" /> : <div className="photo" />;
}

function ValuationPanel({ valuationId, assetId, currency, onChange }: { valuationId: string; assetId: string; currency: string; onChange: () => void }) {
  const [v, setV] = useState<Any | null>(null);
  const [exclude, setExclude] = useState<Record<string, string>>({});
  const [override, setOverride] = useState({ value: "", reason: "" });
  const { busy, error, run } = useAction();

  useEffect(() => {
    setExclude({});
    api("GET", `/api/valuations/${valuationId}`).then(setV);
  }, [valuationId]);
  if (!v) return null;
  const used = v.comparables.filter((c: Any) => c.included);
  const rejected = v.comparables.filter((c: Any) => !c.included);
  const pending = Object.entries(exclude);

  return (
    <Card title={`Valuation · ${label(v.purpose)} · ${v.valuation_date}`} actions={<ConfidenceBadge value={v.confidence} />}>
      {v.status === "concluded" ? (
        <div className="stats">
          <div className="stat">
            <div className="stat-label">Concluded unit value</div>
            <div className="stat-value">{money(v.effective_unit_value_minor, currency)}</div>
            {v.override_id && <div className="stat-sub">Override applied (computed {money(v.unit_value_minor, currency)})</div>}
          </div>
          <div className="stat">
            <div className="stat-label">Mean · Median</div>
            <div className="stat-value small-value">
              {money(v.mean_minor, currency)} · {money(v.median_minor, currency)}
            </div>
          </div>
          <div className="stat">
            <div className="stat-label">Min – Max (range)</div>
            <div className="stat-value small-value">
              {money(v.min_minor, currency)} – {money(v.max_minor, currency)} ({money(v.range_minor, currency)})
            </div>
          </div>
          <div className="stat">
            <div className="stat-label">Dispersion</div>
            <div className="stat-value small-value">{v.dispersion_pct}%</div>
            <div className="stat-sub">{label(v.method_used)} · window {v.window_days}d</div>
          </div>
        </div>
      ) : (
        <div className="note">No adequate comparable sales — no value concluded.</div>
      )}
      {v.flags.map((f: Any) => (
        <div key={f.code} className="note">
          ⚑ <strong>{label(f.code)}</strong>: {f.message}
        </div>
      ))}
      <details>
        <summary>Why “{v.confidence} evidence”?</summary>
        <ul>
          {v.confidence_reasons.map((r: string) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <pre className="factors">{JSON.stringify(v.confidence_factors, null, 2)}</pre>
      </details>
      <h3>Comparables used ({used.length})</h3>
      <div className="table-scroll">
        <table className="table compact">
          <thead>
            <tr>
              <th>Date</th>
              <th>Venue</th>
              <th>Reference</th>
              <th className="num">Amount</th>
              <th className="num">Premium</th>
              <th>FX</th>
              <th className="num">Basis</th>
              <th>Tier</th>
              <th>Exclude (reason required)</th>
            </tr>
          </thead>
          <tbody>
            {used.map((c: Any) => (
              <tr key={c.observation_id} className={c.suspected_outlier ? "outlier" : ""}>
                <td>{c.observed_at}</td>
                <td>
                  {c.venue} <span className="muted small">[{c.source_id}]</span>
                </td>
                <td className="small">{c.source_url ? <a href={c.source_url} target="_blank" rel="noreferrer">{c.source_reference}</a> : c.source_reference}</td>
                <td className="num">{money(c.amount_minor, c.currency)}</td>
                <td className="num">{money(c.buyers_premium_minor, c.currency)}</td>
                <td className="small">{c.fx_rate ? `${Number(c.fx_rate).toFixed(4)} · ${c.fx_source}` : "—"}</td>
                <td className="num">{money(c.basis_amount_base_minor, currency)}</td>
                <td>
                  {c.match_tier}
                  {c.suspected_outlier && <span className="badge conf-limited" title={`${c.deviation_from_median_pct}% from median`}>outlier?</span>}
                </td>
                <td>
                  <input
                    className="reason"
                    placeholder="Reason to exclude…"
                    value={exclude[c.observation_id] ?? ""}
                    onChange={(e) => setExclude({ ...exclude, [c.observation_id]: e.target.value })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pending.some(([, r]) => r.trim()) && (
        <button
          className="primary"
          disabled={busy}
          onClick={() =>
            run(async () => {
              await api("POST", `/api/assets/${assetId}/valuations`, {
                purpose: v.purpose,
                valuationDate: v.purpose === "historical" ? v.valuation_date : undefined,
                supersedesValuationId: v.id,
                exclusions: pending.filter(([, r]) => r.trim()).map(([observationId, reason]) => ({ observationId, reason })),
              });
              onChange();
            })
          }
        >
          Recalculate with documented exclusions
        </button>
      )}
      <details>
        <summary>Evidence considered but not used ({rejected.length})</summary>
        <table className="table compact">
          <tbody>
            {rejected.map((c: Any) => (
              <tr key={c.observation_id}>
                <td>{c.observed_at}</td>
                <td>{c.venue}</td>
                <td className="num">{money(c.amount_minor, c.currency)}</td>
                <td>
                  <code>{c.rejection_code}</code> {c.rejection_detail}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
      <details>
        <summary>Manual override ({v.overrides.length})</summary>
        {v.overrides.map((o: Any) => (
          <div key={o.id} className="note">
            {money(o.override_unit_value_minor, currency)} by {o.overridden_by_name} ({o.overrider_role}) on {o.created_at.slice(0, 10)} — {o.reason}
          </div>
        ))}
        <form
          className="form-row"
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              await api("POST", `/api/valuations/${v.id}/overrides`, { overrideUnitValueMinor: toMinor(override.value), reason: override.reason });
              setOverride({ value: "", reason: "" });
              onChange();
            });
          }}
        >
          <input required inputMode="decimal" placeholder="Unit value" value={override.value} onChange={(e) => setOverride({ ...override, value: e.target.value })} />
          <input required minLength={10} placeholder="Reason (min 10 chars, recorded with your identity)" value={override.reason} onChange={(e) => setOverride({ ...override, reason: e.target.value })} />
          <button disabled={busy}>Record override</button>
        </form>
      </details>
      <ErrorNote error={error} />
      <p className="muted small">
        Methodology {v.methodology_version_id} · performed by {v.performed_by_name} at {v.performed_at} · inputs hash <code>{v.inputs_hash.slice(0, 16)}…</code>
      </p>
    </Card>
  );
}

export function AssetDetail({ id, currency }: { id: string; currency: string }) {
  const [a, setA] = useState<Any | null>(null);
  const [evidence, setEvidence] = useState<Any[]>([]);
  const [sources, setSources] = useState<Any[]>([]);
  const [selectedValuation, setSelectedValuation] = useState<string | null>(null);
  const [panel, setPanel] = useState<"none" | "sell" | "loss" | "grading" | "evidence">("none");
  const [valForm, setValForm] = useState({ purpose: "market", date: today() });
  const [form, setForm] = useState<Any>({});
  const { busy, error, run } = useAction();

  const load = useCallback(async () => {
    const [asset, ev, src] = await Promise.all([api("GET", `/api/assets/${id}`), api("GET", `/api/assets/${id}/evidence`), api("GET", "/api/sources")]);
    setA(asset);
    setEvidence(ev);
    setSources(src);
    setSelectedValuation((cur) => cur ?? asset.valuations[0]?.id ?? null);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (!a) return <ErrorNote error={error} />;
  const held = a.current.heldQuantity > 0;
  const g = a.current.grading;
  const f = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const refresh = async () => {
    setPanel("none");
    setForm({});
    await load();
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <div className="mono muted">{a.asset_ref}</div>
          <h1>{a.card_name}</h1>
          <div className="muted">
            {a.set_name} {a.card_number ? `#${a.card_number}` : ""} · {label(a.game)} · {a.language.toUpperCase()} · {a.edition ?? "—"} · {label(a.variant) || "—"}
          </div>
        </div>
        <div className="head-badges">
          <span className="badge">{label(a.current.status)}</span>
          <span className="badge">{a.product_type === "sealed" ? "Sealed" : g?.grading_company ? `${g.grading_company} ${g.grade}${g.cert_number ? ` · cert ${g.cert_number}` : ""}` : `Raw · ${g?.condition ?? "condition n/a"}`}</span>
          <span className="badge">Insurance: {label(a.current.insuranceStatus)} {a.current.insuredValueMinor ? money(a.current.insuredValueMinor, currency) : ""}</span>
        </div>
      </div>

      <Card title="Actions">
        <div className="button-row">
          {sources
            .filter((s) => s.automatedEvidence)
            .map((s) => (
              <button key={s.id} disabled={busy || !held} onClick={() => run(async () => { await api("POST", `/api/assets/${id}/evidence/import`, { sourceId: s.id }); await load(); })}>
                Import evidence: {s.name}
              </button>
            ))}
          <button disabled={!held} onClick={() => setPanel("evidence")}>Record sale evidence</button>
          <button disabled={!held} onClick={() => setPanel("sell")}>Mark sold</button>
          <button disabled={!held} onClick={() => setPanel("loss")}>Record loss</button>
          {a.product_type !== "sealed" && <button disabled={!held} onClick={() => setPanel("grading")}>Grading change</button>}
          <label className="button">
            Upload photo
            <input type="file" accept="image/*" hidden onChange={(e) => e.target.files?.[0] && run(async () => { await uploadPhoto(id, e.target.files![0]!); await load(); })} />
          </label>
        </div>
        {held && (
          <form
            className="form-row"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                const isPast = valForm.date < today();
                const v = await api("POST", `/api/assets/${id}/valuations`, {
                  purpose: valForm.purpose === "market" && isPast ? "historical" : valForm.purpose,
                  valuationDate: valForm.date,
                });
                setSelectedValuation(v.id);
                await load();
              });
            }}
          >
            <select value={valForm.purpose} onChange={(e) => setValForm({ ...valForm, purpose: e.target.value })}>
              <option value="market">Market value</option>
              <option value="insurance_replacement">Insurance / replacement value</option>
            </select>
            <input type="date" max={today()} value={valForm.date} onChange={(e) => setValForm({ ...valForm, date: e.target.value || today() })} />
            <button className="primary" disabled={busy}>
              {valForm.date < today() ? "Run historical valuation" : "Run valuation"}
            </button>
          </form>
        )}
        {(panel === "sell" || panel === "loss") && (
          <form
            className="form-row"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api("POST", `/api/assets/${id}/${panel === "sell" ? "disposals" : "losses"}`, {
                  effectiveDate: form.date ?? today(),
                  quantity: Number(form.quantity ?? 1),
                  proceedsMinor: panel === "sell" ? toMinor(form.price ?? "0") : null,
                  currency: panel === "sell" ? (form.currency ?? currency) : null,
                  counterparty: form.counterparty || null,
                  reason: form.reason || null,
                });
                await refresh();
              });
            }}
          >
            <input type="date" max={today()} value={form.date ?? today()} onChange={f("date")} />
            <input type="number" min={1} max={a.current.heldQuantity} value={form.quantity ?? 1} onChange={f("quantity")} title="Quantity" />
            {panel === "sell" && <input required inputMode="decimal" placeholder="Sale proceeds" value={form.price ?? ""} onChange={f("price")} />}
            {panel === "sell" && <input pattern="[A-Z]{3}" value={form.currency ?? currency} onChange={f("currency")} />}
            <input placeholder={panel === "sell" ? "Venue / buyer" : "What happened?"} value={form[panel === "sell" ? "counterparty" : "reason"] ?? ""} onChange={f(panel === "sell" ? "counterparty" : "reason")} />
            <button className="primary" disabled={busy}>{panel === "sell" ? "Record disposal" : "Record loss"}</button>
          </form>
        )}
        {panel === "grading" && (
          <form
            className="form-row"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                const graded = Boolean(form.company);
                await api("POST", `/api/assets/${id}/grading`, {
                  effectiveDate: form.date ?? today(),
                  gradingCompany: graded ? form.company : null,
                  grade: graded ? form.grade : null,
                  certNumber: graded ? form.cert || null : null,
                  condition: graded ? null : form.condition ?? "NM",
                  reason: form.reason ?? "graded",
                });
                await refresh();
              });
            }}
          >
            <input type="date" max={today()} value={form.date ?? today()} onChange={f("date")} />
            <select value={form.reason ?? "graded"} onChange={f("reason")}>
              {["graded", "regraded", "cracked", "correction", "condition_change"].map((r) => (
                <option key={r} value={r}>{label(r)}</option>
              ))}
            </select>
            <input placeholder="Company (blank = raw)" value={form.company ?? ""} onChange={f("company")} />
            <input placeholder="Grade" value={form.grade ?? ""} onChange={f("grade")} />
            <input placeholder="Cert #" value={form.cert ?? ""} onChange={f("cert")} />
            <button className="primary" disabled={busy}>Record</button>
          </form>
        )}
        {panel === "evidence" && (
          <form
            className="form-grid"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api("POST", `/api/assets/${id}/evidence`, {
                  kind: form.kind ?? "completed_sale",
                  observedAt: form.date ?? today(),
                  venue: form.venue,
                  amountMinor: toMinor(form.amount ?? "0"),
                  currency: form.currency ?? currency,
                  buyersPremiumMinor: toMinor(form.premium || "0"),
                  sourceReference: form.ref,
                  sourceUrl: form.url || null,
                  gradingCompany: g?.grading_company ?? null,
                  grade: g?.grade ?? null,
                  condition: g?.condition ?? null,
                  armsLength: form.kind === "asking_price" ? null : !form.notArms,
                  verified: Boolean(form.verified),
                });
                await refresh();
              });
            }}
          >
            <label>Type<select value={form.kind ?? "completed_sale"} onChange={f("kind")}><option value="completed_sale">Completed sale</option><option value="asking_price">Asking price (context only)</option></select></label>
            <label>Sale date<input type="date" max={today()} value={form.date ?? today()} onChange={f("date")} /></label>
            <label>Venue<input required value={form.venue ?? ""} onChange={f("venue")} /></label>
            <label>Amount<input required inputMode="decimal" value={form.amount ?? ""} onChange={f("amount")} /></label>
            <label>Buyer's premium<input inputMode="decimal" value={form.premium ?? ""} onChange={f("premium")} /></label>
            <label>Currency<input pattern="[A-Z]{3}" value={form.currency ?? currency} onChange={f("currency")} /></label>
            <label>Transaction ID / lot<input required value={form.ref ?? ""} onChange={f("ref")} /></label>
            <label>Source URL<input type="url" value={form.url ?? ""} onChange={f("url")} /></label>
            <label className="inline"><input type="checkbox" checked={Boolean(form.verified)} onChange={f("verified")} /> I verified this sale completed</label>
            <label className="inline"><input type="checkbox" checked={Boolean(form.notArms)} onChange={f("notArms")} /> Not arm's length</label>
            <div className="span-all"><button className="primary" disabled={busy}>Save evidence</button></div>
          </form>
        )}
        <ErrorNote error={error} />
      </Card>

      {selectedValuation && <ValuationPanel key={selectedValuation} valuationId={selectedValuation} assetId={id} currency={currency} onChange={async () => { setSelectedValuation(null); await load(); }} />}

      <div className="grid2">
        <Card title={`Valuation history (${a.valuations.length})`}>
          <table className="table compact">
            <tbody>
              {a.valuations.map((v: Any) => (
                <tr key={v.id} className={`clickable ${v.id === selectedValuation ? "selected" : ""}`} onClick={() => setSelectedValuation(v.id)}>
                  <td>{v.valuation_date}</td>
                  <td>{label(v.purpose)}</td>
                  <td className="num">{money(v.effective_unit_value_minor, currency)}</td>
                  <td><ConfidenceBadge value={v.status === "concluded" ? v.confidence : null} /></td>
                  <td className="small muted">{v.performed_at.slice(0, 16).replace("T", " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">Valuations are never replaced: each run is kept with its evidence and methodology version.</p>
        </Card>
        <Card title="Ledger events">
          <table className="table compact">
            <tbody>
              {a.ownershipEvents.map((e: Any) => (
                <tr key={e.id}>
                  <td>{e.effective_date}</td>
                  <td>{label(e.event_type)}</td>
                  <td className="num">{e.quantity}</td>
                  <td className="num">{e.amount_minor != null ? money(e.amount_minor, e.currency) : ""}</td>
                  <td className="small muted">{e.counterparty ?? e.reason ?? ""}</td>
                </tr>
              ))}
              {a.gradingHistory.map((r: Any) => (
                <tr key={r.id}>
                  <td>{r.effective_date}</td>
                  <td>grading · {label(r.reason)}</td>
                  <td colSpan={3}>{r.grading_company ? `${r.grading_company} ${r.grade} ${r.cert_number ?? ""}` : `raw ${r.condition ?? ""}`}</td>
                </tr>
              ))}
              {a.insuranceHistory.map((r: Any) => (
                <tr key={`${r.schedule_id}-${r.seq}`}>
                  <td>{r.effective_date}</td>
                  <td>insurance · {label(r.event_type)}</td>
                  <td colSpan={3}>
                    {label(r.change)}: {money(r.previous_value_minor, currency)} → {money(r.new_value_minor, currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">
            Acquired {a.acquisition_date} for {money(a.acquisition_price_minor, a.acquisition_currency)}
            {a.acquisition_source ? ` from ${a.acquisition_source}` : ""}.
          </p>
        </Card>
      </div>

      <Card title={`Market evidence (${evidence.length})`}>
        <div className="table-scroll">
          <table className="table compact">
            <thead>
              <tr><th>Date</th><th>Kind</th><th>Venue</th><th>Grade</th><th className="num">Amount</th><th>Verified</th><th>Arm's length</th><th>Source</th></tr>
            </thead>
            <tbody>
              {evidence.map((o) => (
                <tr key={o.id}>
                  <td>{o.observed_at}</td>
                  <td>{label(o.observation_kind)}</td>
                  <td>{o.venue}</td>
                  <td>{o.grading_company ? `${o.grading_company} ${o.grade}` : (o.condition ?? "raw")}</td>
                  <td className="num">{money(o.amount_minor, o.currency)}</td>
                  <td>{o.verification_status}</td>
                  <td>{o.arms_length == null ? "unknown" : o.arms_length ? "yes" : "no"}</td>
                  <td className="small">{o.source_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {a.photos.length > 0 && (
        <Card title="Photographs">
          <div className="photos">
            {a.photos.map((p: Any) => (
              <Photo key={p.id} id={p.id} />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
