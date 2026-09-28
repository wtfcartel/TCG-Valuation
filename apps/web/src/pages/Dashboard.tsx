import { useEffect, useState } from "react";
import { api } from "../api";
import { navigate } from "../App";
import { HistoryChart, type Point } from "../components/HistoryChart";
import { Card, ConfidenceBadge, ErrorNote, Stat } from "../components/ui";
import { label, money, today } from "../format";

interface Position {
  assetId: string;
  assetRef: string;
  cardName: string;
  setName: string;
  cardNumber: string | null;
  game: string;
  gradingCompany: string | null;
  grade: string | null;
  condition: string | null;
  productType: string;
  heldQuantity: number;
  status: string;
  costBasisMinor: number | null;
  marketValueMinor: number | null;
  confidence: string | null;
  insuredValueMinor: number;
  insuranceStatus: string;
  unrealisedGainMinor: number | null;
  realisedGainMinor: number;
}

interface Portfolio {
  date: string;
  baseCurrency: string;
  totals: Record<string, number>;
  bySet: Array<{ key: string; valueMinor: number; count: number }>;
  byGradingCompany: Array<{ key: string; valueMinor: number; count: number }>;
  byCategory: Array<{ key: string; valueMinor: number; count: number }>;
  largestAssets: Position[];
  positions: Position[];
  warnings: string[];
}

function Breakdown({ title, rows, currency }: { title: string; rows: Portfolio["bySet"]; currency: string }) {
  const total = rows.reduce((s, r) => s + r.valueMinor, 0) || 1;
  return (
    <Card title={title}>
      <table className="table compact">
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td>{label(r.key)}</td>
              <td className="bar-cell">
                <div className="bar" style={{ width: `${(r.valueMinor / total) * 100}%` }} />
              </td>
              <td className="num">{money(r.valueMinor, currency)}</td>
            </tr>
          ))}
          {!rows.length && (
            <tr>
              <td className="muted">No held assets</td>
            </tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}

export function Dashboard({ collection }: { collection: { id: string; base_currency: string } }) {
  const [date, setDate] = useState(today());
  const [p, setP] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<Point[]>([]);
  const [showDisposed, setShowDisposed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ccy = collection.base_currency;

  useEffect(() => {
    api<Portfolio>("GET", `/api/collections/${collection.id}/portfolio?date=${date}`).then(setP, (e) => setError(e.message));
  }, [collection.id, date]);
  useEffect(() => {
    api<{ series: Point[] }>("GET", `/api/collections/${collection.id}/portfolio/history?points=40`).then((r) => setHistory(r.series), () => undefined);
  }, [collection.id]);

  if (!p) return <ErrorNote error={error} />;
  const t = p.totals;
  const positions = p.positions.filter((x) => showDisposed || x.heldQuantity > 0);

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Portfolio</h1>
        <label className="inline">
          As at
          <input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value || today())} />
        </label>
      </div>
      {date !== today() && <div className="note">Point-in-time view: holdings and the valuation records in force on {date}.</div>}
      <div className="stats">
        <Stat label="Market value" value={money(t.marketValueMinor, ccy)} sub={t.unvaluedAssets ? `${t.unvaluedAssets} asset(s) not valued` : undefined} />
        <Stat label="Insured / declared value" value={money(t.insuredValueMinor, ccy)} />
        <Stat label="Acquisition cost (held)" value={money(t.costBasisMinor, ccy)} />
        <Stat label="Unrealised gain / loss" value={money(t.unrealisedGainMinor, ccy)} />
        <Stat label="Realised gain / loss" value={money(t.realisedGainMinor, ccy)} />
      </div>
      {p.warnings.map((w) => (
        <div key={w} className="note">⚠ {w}</div>
      ))}
      <Card title="Portfolio value over time">
        <HistoryChart series={history} currency={ccy} />
      </Card>
      <div className="grid3">
        <Breakdown title="Value by set" rows={p.bySet} currency={ccy} />
        <Breakdown title="Value by grading company" rows={p.byGradingCompany} currency={ccy} />
        <Breakdown title="Value by category" rows={p.byCategory} currency={ccy} />
      </div>
      <Card
        title="Assets"
        actions={
          <label className="inline small">
            <input type="checkbox" checked={showDisposed} onChange={(e) => setShowDisposed(e.target.checked)} /> Show disposed
          </label>
        }
      >
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Asset</th>
                <th>Card</th>
                <th>Grading</th>
                <th className="num">Qty</th>
                <th className="num">Market value</th>
                <th>Evidence</th>
                <th className="num">Insured</th>
                <th className="num">Unrealised</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {positions
                .sort((a, b) => (b.marketValueMinor ?? 0) - (a.marketValueMinor ?? 0))
                .map((x) => (
                  <tr key={x.assetId} className="clickable" onClick={() => navigate({ name: "asset", id: x.assetId })}>
                    <td className="mono">{x.assetRef}</td>
                    <td>
                      <strong>{x.cardName}</strong>
                      <div className="muted small">
                        {x.setName} {x.cardNumber ? `#${x.cardNumber}` : ""} · {label(x.game)}
                      </div>
                    </td>
                    <td>{x.productType === "sealed" ? "Sealed" : x.gradingCompany ? `${x.gradingCompany} ${x.grade}` : `Raw ${x.condition ?? ""}`}</td>
                    <td className="num">{x.heldQuantity}</td>
                    <td className="num">{money(x.marketValueMinor, ccy)}</td>
                    <td>{x.heldQuantity > 0 && <ConfidenceBadge value={x.confidence} />}</td>
                    <td className="num">{money(x.insuredValueMinor, ccy)}</td>
                    <td className="num">{money(x.unrealisedGainMinor, ccy)}</td>
                    <td>{label(x.status)}</td>
                  </tr>
                ))}
              {!positions.length && (
                <tr>
                  <td colSpan={9} className="muted">
                    No assets yet — <a href="#/add">add your first card</a>.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
