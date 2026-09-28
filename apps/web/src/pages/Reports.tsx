import { useCallback, useEffect, useState } from "react";
import { api, download } from "../api";
import { Card, ErrorNote, useAction } from "../components/ui";
import { label } from "../format";

type Any = Record<string, any>;

export function Reports({ collection }: { collection: { id: string } }) {
  const [reports, setReports] = useState<Any[]>([]);
  const [purpose, setPurpose] = useState("market");
  const [json, setJson] = useState<Any | null>(null);
  const { busy, error, run } = useAction();

  const load = useCallback(async () => setReports(await api("GET", `/api/collections/${collection.id}/reports`)), [collection.id]);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="stack">
      <h1>Reports</h1>
      <Card title="Generate a valuation report">
        <div className="form-row">
          <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            <option value="market">Market value</option>
            <option value="insurance_replacement">Insurance / replacement value</option>
          </select>
          <button
            className="primary"
            disabled={busy}
            onClick={() =>
              run(async () => {
                await api("POST", `/api/collections/${collection.id}/reports/valuation`, { purpose });
                await load();
              })
            }
          >
            Generate
          </button>
        </div>
        <p className="muted small">
          The report snapshots the latest valuation records for each held asset. Run valuations first for up-to-date evidence. Insurer
          adjustment reports are generated from the Insurance page.
        </p>
        <ErrorNote error={error} />
      </Card>
      <Card title="Report history (immutable)">
        <table className="table">
          <thead>
            <tr>
              <th>Generated</th>
              <th>Type</th>
              <th>Version</th>
              <th>SHA-256</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.id}>
                <td>{r.generated_at.slice(0, 16).replace("T", " ")}</td>
                <td>{label(r.report_type)}</td>
                <td>v{r.version}</td>
                <td className="mono small">{r.payload_sha256.slice(0, 16)}…</td>
                <td className="button-row">
                  <button onClick={() => run(() => download(`/api/reports/${r.id}/pdf`, `cardcore-${r.report_type}-v${r.version}.pdf`))}>PDF</button>
                  <button onClick={() => run(async () => setJson(await api("GET", `/api/reports/${r.id}`)))}>JSON payload</button>
                </td>
              </tr>
            ))}
            {!reports.length && (
              <tr>
                <td colSpan={5} className="muted">No reports yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
      {json && (
        <Card title={`Payload · integrity ${json.integrity.verified ? "verified ✓" : "FAILED ✗"}`} actions={<button onClick={() => setJson(null)}>Close</button>}>
          <pre className="factors">{JSON.stringify(json.payload, null, 2)}</pre>
        </Card>
      )}
    </div>
  );
}
