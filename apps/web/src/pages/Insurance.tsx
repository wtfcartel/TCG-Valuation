import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Card, ErrorNote, Stat, useAction } from "../components/ui";
import { label, money } from "../format";

type Any = Record<string, any>;

export function Insurance({ collection }: { collection: { id: string; base_currency: string } }) {
  const [schedules, setSchedules] = useState<Any[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Any | null>(null);
  const [form, setForm] = useState({ insurerName: "", policyReference: "", customerReference: "" });
  const [lastReconcile, setLastReconcile] = useState<Any | null>(null);
  const { busy, error, run } = useAction();
  const ccy = collection.base_currency;

  const load = useCallback(async () => {
    const list = await api<Any[]>("GET", `/api/collections/${collection.id}/schedules`);
    setSchedules(list);
    const id = selected ?? list[0]?.id ?? null;
    setSelected(id);
    if (id) setDetail(await api("GET", `/api/schedules/${id}`));
  }, [collection.id, selected]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="stack">
      <h1>Insurance schedule</h1>
      <p className="muted">
        The schedule is a live, append-only ledger. Every change in declared value is an adjustment event with the previous and revised
        value — nothing is overwritten. Cardcore does not calculate premiums; the insurer decides when changes apply.
      </p>
      {schedules.length === 0 && (
        <Card title="Create a schedule">
          <form
            className="form-grid"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api("POST", `/api/collections/${collection.id}/schedules`, {
                  insurerName: form.insurerName || null,
                  policyReference: form.policyReference || null,
                  customerReference: form.customerReference || null,
                });
                await load();
              });
            }}
          >
            <label>Insurer<input value={form.insurerName} onChange={(e) => setForm({ ...form, insurerName: e.target.value })} /></label>
            <label>Policy reference<input value={form.policyReference} onChange={(e) => setForm({ ...form, policyReference: e.target.value })} /></label>
            <label>Customer reference<input value={form.customerReference} onChange={(e) => setForm({ ...form, customerReference: e.target.value })} /></label>
            <div className="span-all"><button className="primary" disabled={busy}>Create schedule</button></div>
          </form>
        </Card>
      )}
      {detail && (
        <>
          <div className="stats">
            <Stat label="Declared value" value={money(detail.declaredValueMinor, ccy)} />
            <Stat label="Scheduled assets" value={String(detail.scheduledAssets.length)} />
            <Stat label="Insurer" value={detail.schedule.insurer_name ?? "—"} sub={`Policy ${detail.schedule.policy_reference ?? "—"}`} />
            <Stat label="Event chain" value={detail.chain.valid ? "✓ intact" : `✗ broken at #${detail.chain.brokenAtSeq}`} />
          </div>
          <Card
            title="Adjustment events"
            actions={
              <>
                <button
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      setLastReconcile(await api("POST", `/api/schedules/${selected}/reconcile`));
                      await load();
                    })
                  }
                >
                  Reconcile & revalue
                </button>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api("POST", `/api/schedules/${selected}/reports/adjustment`, {});
                      location.hash = "/reports";
                    })
                  }
                >
                  Generate insurer report
                </button>
              </>
            }
          >
            {lastReconcile && (
              <div className="note">
                Reconciliation created {lastReconcile.events.length} event(s).
                {lastReconcile.unvalued.length > 0 && ` Not valued (insufficient evidence): ${lastReconcile.unvalued.join(", ")}.`}
              </div>
            )}
            <ErrorNote error={error} />
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Type</th>
                    <th>Effective</th>
                    <th>Reason</th>
                    <th className="num">Previous</th>
                    <th className="num">Revised</th>
                    <th>Assets</th>
                    <th>Hash</th>
                  </tr>
                </thead>
                <tbody>
                  {[...detail.events].reverse().map((e: Any) => (
                    <tr key={e.id}>
                      <td>{e.seq}</td>
                      <td>{label(e.event_type)}</td>
                      <td>{e.effective_date}</td>
                      <td>{e.reason}</td>
                      <td className="num">{money(e.previous_declared_minor, ccy)}</td>
                      <td className="num">{money(e.revised_declared_minor, ccy)}</td>
                      <td className="small">
                        {e.lines.map((l: Any) => (
                          <div key={l.id}>
                            {l.asset_ref} {label(l.change)} {money(l.previous_value_minor, ccy)} → {money(l.new_value_minor, ccy)}
                          </div>
                        ))}
                      </td>
                      <td className="mono small">{e.event_hash.slice(0, 10)}</td>
                    </tr>
                  ))}
                  {!detail.events.length && (
                    <tr>
                      <td colSpan={8} className="muted">No events yet — run “Reconcile & revalue” to declare the collection.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
          <Card title="Insurer notification rules (recorded for later)">
            <pre className="factors">{JSON.stringify(detail.schedule.notification_rules, null, 2)}</pre>
          </Card>
        </>
      )}
    </div>
  );
}
