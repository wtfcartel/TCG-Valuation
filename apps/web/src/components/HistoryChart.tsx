import { useMemo, useRef, useState } from "react";
import { money } from "../format";

export interface Point {
  date: string;
  marketValueMinor: number;
  insuredValueMinor: number;
  costBasisMinor: number;
  heldAssets?: number;
  unvaluedAssets?: number;
}

const SERIES = [
  { key: "marketValueMinor", label: "Market value", color: "var(--series-1)", dash: undefined },
  { key: "insuredValueMinor", label: "Insured value", color: "var(--series-2)", dash: undefined },
  { key: "costBasisMinor", label: "Cost basis", color: "var(--series-3)", dash: "5 4" },
] as const;

function niceMax(v: number): number {
  if (v <= 0) return 100;
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / p) * p;
}

/** Single-axis line chart, three series in one unit, with crosshair tooltip and direct end labels. */
export function HistoryChart({ series, currency }: { series: Point[]; currency: string }) {
  const W = 760;
  const H = 260;
  const pad = { l: 72, r: 110, t: 12, b: 28 };
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const { max, x, y } = useMemo(() => {
    const max = niceMax(Math.max(...series.flatMap((p) => [p.marketValueMinor, p.insuredValueMinor, p.costBasisMinor])));
    const x = (i: number) => pad.l + (series.length <= 1 ? 0 : (i / (series.length - 1)) * (W - pad.l - pad.r));
    const y = (v: number) => pad.t + (1 - v / max) * (H - pad.t - pad.b);
    return { max, x, y };
  }, [series]);

  if (series.length < 2) return <p className="muted">Not enough history yet.</p>;

  const onMove = (e: React.PointerEvent) => {
    const rect = svgRef.current!.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (series.length - 1));
    setHover(Math.max(0, Math.min(series.length - 1, i)));
  };

  const last = series[series.length - 1]!;
  // Direct end labels: stack in value order with a minimum 14px gap so they never collide.
  const endLabels = SERIES.map((s) => ({ key: s.key, label: s.label, y: y(last[s.key]) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < endLabels.length; i += 1) {
    endLabels[i]!.y = Math.max(endLabels[i]!.y, endLabels[i - 1]!.y + 14);
  }
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const hp = hover != null ? series[hover]! : null;

  return (
    <div className="viz-root chart-wrap">
      <div className="legend">
        {SERIES.map((s) => (
          <span key={s.key}>
            <svg width="18" height="8" aria-hidden>
              <line x1="0" y1="4" x2="18" y2="4" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} />
            </svg>
            {s.label}
          </span>
        ))}
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="chart"
        role="img"
        aria-label="Portfolio market, insured and cost-basis value over time"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className="grid" />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="axis-label">
              {money(t, currency).replace(/\.00$/, "")}
            </text>
          </g>
        ))}
        {[0, Math.floor((series.length - 1) / 2), series.length - 1].map((i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === series.length - 1 ? "end" : "middle"} className="axis-label">
            {series[i]!.date}
          </text>
        ))}
        {SERIES.map((s) => (
          <path
            key={s.key}
            d={series.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[s.key]).toFixed(1)}`).join("")}
            fill="none"
            stroke={s.color}
            strokeWidth="2"
            strokeDasharray={s.dash}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}
        {endLabels.map((l) => (
          <text key={l.key} x={W - pad.r + 8} y={l.y} className="end-label" dominantBaseline="middle">
            {l.label}
          </text>
        ))}
        {hp && hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={H - pad.b} className="crosshair" />
            {SERIES.map((s) => (
              <circle key={s.key} cx={x(hover)} cy={y(hp[s.key])} r="4.5" fill={s.color} stroke="var(--surface-1)" strokeWidth="2" />
            ))}
          </g>
        )}
      </svg>
      <p className="muted small">
        Market value is the valuation record in force on each date. Assets without a valuation on a date are counted as unvalued, not
        as zero-value evidence.
      </p>
      {hp && hover != null && (
        <div className="tooltip" style={{ left: `${(x(hover) / W) * 100}%` }}>
          <strong>{hp.date}</strong>
          {SERIES.map((s) => (
            <div key={s.key}>
              <span className="swatch" style={{ background: s.color }} /> {s.label}: {money(hp[s.key], currency)}
            </div>
          ))}
          {Boolean(hp.unvaluedAssets) && (
            <div className="muted">
              {hp.unvaluedAssets} of {hp.heldAssets} held asset(s) had no valuation in force
            </div>
          )}
        </div>
      )}
    </div>
  );
}
